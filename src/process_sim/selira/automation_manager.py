"""Experimental SC-01 lifecycle orchestration over local RDF snapshots.

Full compiled SHACL remains the admission gate. Selective reference evaluation
is measured separately; it is not an incremental SHACL execution engine.
Evidence flags are caller attestations for the proposed snapshot.
"""
import json
from pathlib import Path
from threading import RLock

from rdflib import Graph, RDF, URIRef
from process_sim.safsl.shacl.compiler import compile_contract
from process_sim.safsl.shacl.admission import VersionedGraphStore, admit, Decision, Verdict
from .reassessment.snapshot import Snapshot
from .reassessment.selective_sc01 import compare


class AutomationManager:
    def __init__(self, source_path, bindings_path):
        self.shapes, self.manifest = compile_contract(
            Path(source_path).read_text(encoding="utf-8"),
            json.loads(Path(bindings_path).read_text(encoding="utf-8")))
        self.contract, = self.manifest["contracts"]
        self.store = VersionedGraphStore()
        self._lock = RLock()
        self.history = []

    def _project(self, graph, revision, complete):
        c = self.contract
        focus = URIRef(c["focus_predicate"])
        catalog = URIRef(c["catalog_predicate"])
        assets = set(graph.subjects(RDF.type, URIRef(c["focus_class"])))
        assigned = set(graph.subjects(focus, None))
        if not assigned <= assets:
            raise ValueError("Non-asset focus nodes")
        def mapping(nodes, predicate):
            result = {}
            for node in nodes:
                values = {str(v) for v in graph.objects(node, predicate)}
                if len(values) != 1 or not next(iter(values), ""):
                    raise ValueError("Projection requires one nonempty identifier per resource")
                result[str(node)] = next(iter(values))
            return result
        products = set(graph.subjects(RDF.type, URIRef(c["catalog_class"])))
        return Snapshot(str(revision), mapping(assigned, focus),
                        mapping(products, catalog), complete=complete)

    def submit(self, candidate, *, expected_version, evidence_complete=(),
               identity_normalized=False, applicability_confirmed=False,
               coverage_attested=False, policy_unchanged=False,
               authority_unchanged=False):
        """Submit a complete candidate graph, not a mutation of the admitted graph."""
        with self._lock:
            current, version = self.store.snapshot()
            proposed = Graph()
            proposed += candidate
            evidence = set(evidence_complete)
            complete = set(self.contract["requires_complete"]) <= evidence
            report = None
            if expected_version != version:
                decision = Decision(Verdict.U, False, "Stale snapshot version", version)
            else:
                try:
                    before = self._project(current, version, version > 0)
                    after = self._project(proposed, version + 1, complete)
                    if not after.assigned:
                        decision = Decision(Verdict.NA if applicability_confirmed and complete and identity_normalized else Verdict.U,
                                            False, "Empty assigned focus population", version)
                    else:
                        if version > 0 and applicability_confirmed and identity_normalized:
                            report = compare(before, after, coverage_attested=coverage_attested,
                                             policy_unchanged=policy_unchanged,
                                             authority_unchanged=authority_unchanged)
                        if report is not None and not report.equivalent:
                            decision = Decision(Verdict.U, False, "Reassessment disagreement", version)
                        else:
                            decision = admit(self.store, shapes_ttl=self.shapes,
                                             manifest=self.manifest,
                                             changed_template_ids=self.contract["dependencies"],
                                             additions=set(proposed) - set(current),
                                             removals=set(current) - set(proposed),
                                             evidence_complete=evidence,
                                             expected_version=version,
                                             identity_normalized=identity_normalized,
                                             applicability_confirmed=applicability_confirmed)
                except ValueError as exc:
                    decision = Decision(Verdict.U, False, str(exc), version)
            record = {"from_version": version, "version": decision.version,
                      "verdict": decision.verdict.value, "committed": decision.committed,
                      "reason": decision.reason,
                      "reassessment": None if report is None else {
                          "affected": sorted(report.affected),
                          "selective_evaluations": report.selective_evaluations,
                          "full_evaluations": report.full_evaluations,
                          "equivalent": report.equivalent,
                          "full_fallback": report.full_fallback}}
            self.history.append(record)
            return record
