"""Local transactional SC-01 admission for lifted AAS evidence.

SQLite is the only transaction boundary. No GraphDB/AAS writes or distributed CAS.
"""
from rdflib import Graph

from .lifted_sc01 import compile_lifted_sc01
from .sqlite_admission import SQLiteAdmissionStore


def admit_lifted_snapshot(filename, *, graph: Graph, provenance: dict,
                          source_revisions: dict, evidence_complete=False,
                          identity_normalized=False, applicability_confirmed=True):
    """Replace the local candidate RDF snapshot, validate, and commit if V.

    Source revision tokens and completeness are supplied by the caller; this
    function does not verify upstream freshness. Reject on any missing evidence.
    """
    if not isinstance(graph, Graph):
        raise TypeError("graph must be an rdflib.Graph")
    if not isinstance(provenance, dict):
        raise TypeError("provenance required")
    shapes_ttl, manifest = compile_lifted_sc01(provenance)
    store = SQLiteAdmissionStore(filename)
    previous, version, _ = store.snapshot()
    additions = set(graph) - set(previous)
    removals = set(previous) - set(graph)
    required = [provenance["assetinventory"]["template_id"],
                provenance["productcatalog"]["template_id"]]
    return store.admit(
        shapes_ttl=shapes_ttl, manifest=manifest,
        changed_template_ids=required, source_revisions=source_revisions,
        expected_version=version, additions=additions, removals=removals,
        evidence_complete=required if evidence_complete else (),
        identity_normalized=identity_normalized,
        applicability_confirmed=applicability_confirmed,
    )
