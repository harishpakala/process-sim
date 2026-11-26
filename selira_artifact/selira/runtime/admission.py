"""Fail-closed SC-01 admission with versioned in-memory compare-and-commit.

This is a reference coordinator for a single-process store, NOT an atomic
transaction implementation for remote GraphDB/AAS repositories.
"""

# Created: 2026-10-31
# Author: Harish
from dataclasses import dataclass
from enum import Enum
from threading import RLock

from rdflib import Graph, RDF, URIRef
from pyshacl import validate


class Verdict(str, Enum):
    V = "V"
    F = "F"
    U = "U"
    NA = "NA"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    committed: bool
    reason: str
    version: int


class VersionedGraphStore:
    """Single-process snapshot store; every update is protected by a lock."""
    def __init__(self, graph=None):
        self._lock = RLock()
        self._graph = Graph()
        if graph is not None:
            self._graph += graph
        self._version = 0

    def snapshot(self):
        with self._lock:
            copy = Graph()
            copy += self._graph
            return copy, self._version

    def compare_and_commit(self, expected_version, graph):
        with self._lock:
            if expected_version != self._version:
                return False, self._version
            copy = Graph()
            copy += graph
            self._graph = copy
            self._version += 1
            return True, self._version


def affected_contracts(manifest, changed_template_ids):
    """Conservatively revalidate when ANY declared dependency changes."""
    changed = set(changed_template_ids)
    return [c for c in manifest["contracts"]
            if changed.intersection(c["dependencies"])]


def admit(store, *, shapes_ttl, manifest, changed_template_ids, additions=(),
          removals=(), evidence_complete=None, expected_version=None,
          identity_normalized=False, applicability_confirmed=True):
    """Validate the resulting snapshot and atomically commit to this store.

    evidence_complete: caller-attested IDs of complete authoritative scopes
    for THIS snapshot; compiler configuration is never treated as evidence.
    Fail closed on missing scope, stale version, missing identity normalization,
    no focus nodes, SHACL errors, or a non-V verdict.
    """
    current, version = store.snapshot()
    if expected_version is not None and expected_version != version:
        return Decision(Verdict.U, False, "Stale snapshot version", version)
    relevant = affected_contracts(manifest, changed_template_ids)
    if not relevant:
        return Decision(Verdict.NA, False, "No affected contract; separate update policy required", version)
    candidate = Graph()
    candidate += current
    for triple in removals:
        candidate.remove(triple)
    for triple in additions:
        candidate.add(triple)
    if not applicability_confirmed:
        return Decision(Verdict.U, False, "Contract applicability unconfirmed", version)
    if not identity_normalized:
        return Decision(Verdict.U, False, "Canonical identity normalization unconfirmed", version)
    evidence = set(evidence_complete or ())
    required = set().union(*(set(c["requires_complete"]) for c in relevant))
    if not required.issubset(evidence):
        return Decision(Verdict.U, False, "Authoritative evidence incomplete", version)
    if not all(any(candidate.subjects(RDF.type, URIRef(c["focus_class"]))) for c in relevant):
        return Decision(Verdict.NA, False, "Empty focus population", version)
    try:
        shapes = Graph().parse(data=shapes_ttl, format="turtle")
        # The compiler's SHACL shape set is assumed to contain precisely
        # these mandatory contracts; reject unexpected manifest mismatches.
        for c in relevant:
            if (URIRef(c["shape"]), RDF.type, URIRef("http://www.w3.org/ns/shacl#NodeShape")) not in shapes:
                return Decision(Verdict.U, False, "Missing mandatory shape", version)
        conforms, _, _ = validate(data_graph=candidate, shacl_graph=shapes,
                                   inference="none", advanced=False,
                                   abort_on_first=False)
    except Exception as exc:
        return Decision(Verdict.U, False, f"Validation error: {exc}", version)
    if not conforms:
        return Decision(Verdict.F, False, "Integrity contract violated", version)
    committed, new_version = store.compare_and_commit(version, candidate)
    if not committed:
        return Decision(Verdict.U, False, "Concurrent update; revalidate", new_version)
    return Decision(Verdict.V, True, "Validated and committed", new_version)
