"""Regression for canonical Engineering LocalID query, not historian mapping."""
from dataclasses import replace

from process_sim.api.unified_semantic_interpreter import interpret_unified_semantics
from process_sim.api.unified_graph_compiler import compile_unified_graph_query


D = "https://example.org/dexpi/"


class EngineeringSchema:
    concepts = [{"kind": "shape", "domain": "dexpi", "uri": "shape:dexpi"}]
    by_uri = {}

    def shacl_paths(self, root, max_depth=5, domain=None):
        if (root, domain) != ("shape:dexpi", "dexpi"):
            return []
        return [[{"property": predicate, "evidence_ids": []}
                 for predicate in path]
                for path in [
                    (D + "hasInstrumentationFunction", D + "hasLocalId"),
                    (D + "hasInstrumentationFunction", D + "hasAssetIdentifier"),
                ]]


def test_localid_question_never_projects_signalname_or_assetidentifier():
    question = "Show dexpi InstrumentationFunction localId where localId is FI_103."
    captured = []
    calls = []
    def confused_model(q, catalog, context):
        calls.append(q)
        # Reproduce Qwen's incorrect SignalName projection on AssetIdentifier.
        return {
            "projections": [{"name": "SignalName", "path_id": 1,
                             "source": "graphdb", "alias": "entity"}],
            "joins": [], "where": None, "group_by": [],
            "aggregation": None, "order_by": [], "limit": None,
            "sources": ["graphdb"], "run_id": None,
            "start_seconds": None, "end_seconds": None,
        }
    plan = interpret_unified_semantics(
        question, EngineeringSchema(), interpret=confused_model,
        raw_output=captured.append)
    assert len(calls) == 1
    assert captured[0]["projections"][0]["name"] == "SignalName"
    assert plan.validated
    assert plan.sources == ("graphdb",)
    assert len(plan.projections) == 1
    assert plan.projections[0].name == "LocalID"
    assert plan.projections[0].path.predicates == (
        D + "hasInstrumentationFunction", D + "hasLocalId")
    assert plan.where.value == "FI_103"
    assert plan.where.path == plan.projections[0].path
    graph_plan = replace(plan, sources=("graphdb",), validated=True)
    sparql = compile_unified_graph_query(graph_plan)
    assert D + "hasLocalId" in sparql
    assert "FI_103" in sparql
    assert "hasSignalName" not in sparql
    assert "hasAssetIdentifier" not in sparql
