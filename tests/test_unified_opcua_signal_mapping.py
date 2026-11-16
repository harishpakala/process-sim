"""Regression: OPCUA SignalMapping lookup is one SHACL root, no join."""
from process_sim.api.unified_semantic_interpreter import interpret_unified_semantics
from process_sim.api.unified_graph_compiler import compile_unified_graph_query

O = "https://example.org/opcuaconnectivity/"
QUESTION = ("Show opcuaconnectivity SignalMapping signalName where assetIdentifier "
            "is https://aas.example.com/FI103.")


class Schema:
    concepts = [{"kind": "shape", "domain": "opcuaconnectivity", "uri": "shape:opcua"}]
    by_uri = {}
    def shacl_paths(self, root, max_depth=5, domain=None):
        if (root, domain) != ("shape:opcua", "opcuaconnectivity"):
            return []
        return [[{"property": p, "evidence_ids": []} for p in path]
                for path in [(O + "hasSignalName",), (O + "hasAssetIdentifier",)]]


def test_signal_mapping_uses_one_root_and_no_join():
    calls = []
    def confused_model(q, catalog, context):
        calls.append(q)
        return {
            "projections": [{"name": "SignalName", "path_id": 0,
                             "source": "graphdb", "alias": "opcuaconnectivity"}],
            "joins": [{"left": "opcuaconnectivity", "right": "other",
                       "left_path_id": 1, "right_path_id": 0}],
            "where": None, "group_by": [], "aggregation": None,
            "order_by": [], "limit": None, "sources": ["graphdb"],
            "run_id": None, "start_seconds": None, "end_seconds": None,
        }
    plan = interpret_unified_semantics(QUESTION, Schema(), interpret=confused_model)
    assert len(calls) == 1
    assert plan.validated
    assert plan.sources == ("graphdb",)
    assert plan.joins == ()
    assert plan.projections[0].name == "SignalName"
    assert plan.where.value == "https://aas.example.com/FI103"
    assert plan.where.alias == plan.projections[0].alias
    query = compile_unified_graph_query(plan)
    assert O + "hasSignalName" in query
    assert O + "hasAssetIdentifier" in query
    assert "https://aas.example.com/FI103" in query
    assert "join_0" not in query


def test_signal_name_without_signal_mapping_is_graph_only_even_if_qwen_routes_historian():
    question = ("Show opcuaconnectivity signalName where assetIdentifier "
                "is https://aas.example.com/FI103.")
    def wrong_historian(q, catalog, context):
        return {
            "projections": [{"name": "SignalName", "path_id": 0,
                             "source": "graphdb", "alias": "opcuaconnectivity"}],
            "joins": [], "where": None, "group_by": [], "aggregation": None,
            "order_by": [], "limit": None,
            "sources": ["graphdb", "timescaledb"],
            "run_id": None, "start_seconds": None, "end_seconds": None,
        }
    plan = interpret_unified_semantics(question, Schema(), interpret=wrong_historian)
    assert plan.sources == ("graphdb",)
    assert plan.joins == ()
    assert plan.run_id is None
    assert plan.where.value == "https://aas.example.com/FI103"
    assert "hasAssetIdentifier" in compile_unified_graph_query(plan)
