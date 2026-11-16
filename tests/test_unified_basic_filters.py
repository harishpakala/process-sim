"""Seven basic GraphDB filter regressions using one SHACL-grounded mechanism."""
import pytest
from process_sim.api.unified_semantic_interpreter import interpret_unified_semantics
from process_sim.api.unified_graph_compiler import compile_unified_graph_query
from process_sim.api.unified_semantic_ir import BooleanExpression

BASE = "https://example.org/"


class Schema:
    concepts = [
        {"kind": "shape", "domain": domain, "uri": "shape:" + domain}
        for domain in ("dexpi", "opcuaconnectivity", "assetinventory")
    ]
    by_uri = {}

    def shacl_paths(self, root, max_depth=5, domain=None):
        paths = {
            "dexpi": [
                ("hasInstrumentationFunction", "hasLocalId"),
                ("hasInstrumentationFunction", "hasMeasuredVariable"),
            ],
            "opcuaconnectivity": [
                ("hasSignalMapping", "hasSignalName"),
                ("hasSignalMapping", "hasAssetIdentifier"),
                ("hasSignalMapping", "hasSignalDirection"),
                ("hasSignalMapping", "hasMappingStatus"),
            ],
            "assetinventory": [
                ("hasAsset", "hasAssetName"),
                ("hasAsset", "hasAssetIdentifier"),
            ],
        }
        if root != "shape:" + str(domain):
            return []
        return [[{"property": BASE + domain + "/" + p, "evidence_ids": []}
                 for p in path] for path in paths.get(domain, [])]


QUESTIONS = [
    "Show opcuaconnectivity SignalMapping signalName where assetIdentifier is https://aas.example.com/FI103.",
    "Show dexpi InstrumentationFunction localId where localId is FI_103.",
    "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
    "Show opcuaconnectivity SignalMapping signalName where signalDirection is READ.",
    "Show assetinventory Asset assetName where assetIdentifier is https://aas.example.com/FI103.",
    ("Show opcuaconnectivity SignalMapping signalName where assetIdentifier is "
     "https://aas.example.com/FI103 and mappingStatus is PROVISIONAL_ENGINEERING_MATCH."),
    ("Show opcuaconnectivity SignalMapping signalName where assetIdentifier is "
     "https://aas.example.com/FI103 or assetIdentifier is https://aas.example.com/FI104."),
]


@pytest.mark.parametrize("question", QUESTIONS)
def test_basic_filters_are_graph_only_and_compile(question):
    calls = []
    def confused_model(q, catalog, context):
        calls.append(q)
        return {
            "projections": [{"name": "SignalName", "path_id": 0,
                             "source": "graphdb", "alias": "wrong"}],
            "joins": [], "where": None, "group_by": [],
            "aggregation": None, "order_by": [], "limit": None,
            "sources": ["graphdb", "timescaledb"],
            "run_id": None, "start_seconds": None, "end_seconds": None,
        }
    plan = interpret_unified_semantics(question, Schema(), interpret=confused_model)
    assert len(calls) == 1
    assert plan.validated
    assert plan.sources == ("graphdb",)
    assert plan.joins == ()
    assert plan.run_id is None
    query = compile_unified_graph_query(plan)
    assert "SELECT DISTINCT" in query
    assert "hasSignalName" in query if "signalName" in question else True
    if " and " in question:
        assert isinstance(plan.where, BooleanExpression)
        assert plan.where.operator == "and"
        assert "&&" in query
    if " or " in question:
        assert isinstance(plan.where, BooleanExpression)
        assert plan.where.operator == "or"
        assert "||" in query
    if "FI103" in question:
        assert "https://aas.example.com/FI103" in query
