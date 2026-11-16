"""Offline compiler tests; GraphDB network calls are mocked."""
import pytest
from process_sim.api.unified_semantic_ir import (
    GraphPath, Projection, Predicate, BooleanExpression, Join, SemanticQuery,
)
from process_sim.api.unified_graph_compiler import (
    compile_unified_graph_query, execute_unified_graph_query,
)

URI = "https://example.org/dexpi/hasAssetIdentifier"


class Schema:
    def shacl_paths(self, root, max_depth=1, domain=None):
        return [[{"property": URI, "evidence_ids": ["p", "path"]}]]


def query(**kwargs):
    values = dict(question="Show asset identifiers from DEXPI entities",
                  projections=(Projection("assetIdentifier",
                      GraphPath("DEXPI", "shape:instrument", (URI,))),))
    values.update(kwargs)
    return SemanticQuery(**values).validate(Schema())


def test_compiles_validated_projection_to_bounded_select():
    sparql = compile_unified_graph_query(query())
    assert sparql.startswith("SELECT DISTINCT ?assetIdentifier WHERE")
    assert "<" + URI + ">" in sparql
    assert "LIMIT 100" in sparql


def test_compiles_nested_boolean_filter():
    plan = query(where=BooleanExpression("not", (
        Predicate("assetIdentifier", "eq", "FI_105"),)))
    sparql = compile_unified_graph_query(plan)
    assert '"FI_105"' in sparql
    assert "FILTER((!" in sparql


def test_injection_is_quoted_as_literal():
    plan = query(where=Predicate("assetIdentifier", "eq", '" } DELETE WHERE { ?s ?p ?o }'))
    sparql = compile_unified_graph_query(plan)
    assert '\\"' in sparql


def test_unvalidated_plan_rejected():
    with pytest.raises(ValueError, match="validated"):
        compile_unified_graph_query(SemanticQuery(
            "Show asset identifiers from DEXPI entities",
            (Projection("assetIdentifier", GraphPath("DEXPI", "shape:instrument", (URI,))),)))


def test_unsupported_aggregation_fails_closed():
    with pytest.raises(ValueError, match="Aggregation"):
        compile_unified_graph_query(query(aggregation="count"))


def test_join_only_alias_is_allowed_when_connected_to_projected_entity():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    plan = query(projections=(Projection("assetIdentifier", path, alias="signal"),),
                 joins=(Join("engineering", "signal", path, path),))
    sparql = compile_unified_graph_query(plan)
    assert "?root_engineering <" + URI + ">" in sparql
    assert "FILTER(?join_0_left_0 = ?join_0_right_0)" in sparql
    assert sparql.startswith("SELECT DISTINCT ?assetIdentifier WHERE")


def test_disconnected_join_only_aliases_fail_closed():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    plan = query(projections=(Projection("assetIdentifier", path, alias="signal"),),
                 joins=(Join("engineering", "other", path, path),))
    with pytest.raises(ValueError, match="Cartesian"):
        compile_unified_graph_query(plan)


def test_mixed_query_not_silently_reduced_to_graph():
    plan = query(sources=("graphdb", "timescaledb"),
                 run_id="00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValueError, match="Cross-source"):
        compile_unified_graph_query(plan)


def test_executor_checks_response_columns():
    plan = query()
    result = execute_unified_graph_query(
        plan, "http://unused", executor=lambda endpoint, sparql:
        [{"assetIdentifier": "A-1"}])
    assert result["rows"] == [{"assetIdentifier": "A-1"}]
    with pytest.raises(ValueError, match="unexpected columns"):
        execute_unified_graph_query(plan, "http://unused",
                                     executor=lambda endpoint, sparql: [{"wrong": "A-1"}])


def test_real_join_is_anchored_to_projection_roots():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    plan = query(projections=(
        Projection("leftId", path, alias="left"),
        Projection("rightId", path, alias="right"),
    ), joins=(Join("left", "right", path, path),))
    sparql = compile_unified_graph_query(plan)
    assert "?root_left <" + URI + ">" in sparql
    assert "?root_right <" + URI + ">" in sparql
    assert "FILTER(?join_0_left_0 = ?join_0_right_0)" in sparql


def test_disconnected_roots_rejected():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    plan = query(projections=(
        Projection("leftId", path, alias="left"),
        Projection("rightId", path, alias="right"),
    ))
    with pytest.raises(ValueError, match="Cartesian"):
        compile_unified_graph_query(plan)


def test_multiple_properties_share_one_root_without_join():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    plan = query(projections=(
        Projection("id1", path, alias="instrument"),
        Projection("id2", path, alias="instrument"),
    ))
    sparql = compile_unified_graph_query(plan)
    assert sparql.count("?root_instrument <" + URI + ">") == 2


def test_h6_nonprojected_localid_filter_uses_joined_instrument_root():
    dexpi = "https://example.org/dexpi/"
    opc = "https://example.org/opcuaconnectivity/"
    root = "shape:dexpi"
    mapping = "shape:opcua"
    local = GraphPath("dexpi", root, (dexpi + "hasInstrumentationFunction",
                                       dexpi + "hasLocalId"))
    asset = GraphPath("dexpi", root, (dexpi + "hasInstrumentationFunction",
                                       dexpi + "hasAssetIdentifier"))
    op_asset = GraphPath("opcuaconnectivity", mapping, (opc + "hasAssetIdentifier",))
    signal = GraphPath("opcuaconnectivity", mapping, (opc + "hasSignalName",))
    class H6Schema:
        def shacl_paths(self, shape, max_depth=5, domain=None):
            paths = (local, asset, op_asset, signal)
            return [[{"property": pred, "evidence_ids": []} for pred in p.predicates]
                    for p in paths if p.root_shape == shape and p.domain == domain
                    and len(p.predicates) <= max_depth]
    plan = SemanticQuery(
        question="How did DEXPI InstrumentationFunction with LocalID FI_103 behave during simulation run?",
        projections=(Projection("SignalName", signal, alias="opcuaconnectivity"),),
        joins=(Join("dexpi", "opcuaconnectivity", asset, op_asset),),
        where=Predicate("hasLocalId", "eq", "FI_103", local, "dexpi"),
    ).validate(H6Schema())
    sparql = compile_unified_graph_query(plan)
    assert "?root_dexpi <" + dexpi + "hasInstrumentationFunction> ?filter_0_0 ." in sparql
    assert "?filter_0_0 <" + dexpi + "hasLocalId> ?filter_0_1 ." in sparql
    assert "?root_dexpi <" + dexpi + "hasInstrumentationFunction> ?join_0_left_0 ." in sparql
    assert "?join_0_left_0 <" + dexpi + "hasAssetIdentifier> ?join_0_left_1 ." in sparql
    assert 'FILTER((?filter_0_1 = "FI_103"))' in sparql
    assert sparql.startswith("SELECT DISTINCT ?SignalName WHERE")


def test_nonprojected_filter_on_unbound_root_rejected():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    with pytest.raises(ValueError, match="bound entity alias"):
        SemanticQuery(
            question="Show asset identifiers for a filtered instrument",
            projections=(Projection("assetIdentifier", path),),
            where=Predicate("hasAssetIdentifier", "eq", "A", path, "other"),
        ).validate(Schema())
