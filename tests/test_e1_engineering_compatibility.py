"""E1 engineering compatibility baseline.

Offline tests for the new compiler plus the original Engineering API contract.
These are structural regression checks, not proof of equivalent answers on live
GraphDB data. Legacy and unified execution must remain separate until parity.
"""
import pytest

from process_sim.api import dtwise_query
from process_sim.api.unified_graph_compiler import compile_unified_graph_query
from process_sim.api.unified_semantic_ir import (
    BooleanExpression, GraphPath, Join, Predicate, Projection, SemanticQuery,
)

D = "https://example.org/dexpi/"
O = "https://example.org/opcuaconnectivity/"
ROOT = "shape:instrument"
OPC_ROOT = "shape:opcua"


class EngineeringSchema:
    def shacl_paths(self, root, max_depth=5, domain=None):
        paths = {
            ("DEXPI", ROOT): [
                (D + "hasInstrumentationFunction", D + "hasLocalId"),
                (D + "hasInstrumentationFunction", D + "hasAssetIdentifier"),
                (D + "hasInstrumentationFunction", D + "hasProductIdentifier"),
            ],
            ("OPCUAConnectivity", OPC_ROOT): [
                (O + "hasAssetIdentifier",),
                (O + "hasSignalName",),
            ],
        }
        return [
            [{"property": predicate, "evidence_ids": ["shacl:edge"]}
             for predicate in predicates]
            for predicates in paths.get((domain, root), ())
            if len(predicates) <= max_depth
        ]


def dexpi(name):
    return GraphPath("DEXPI", ROOT, (
        D + "hasInstrumentationFunction", D + "has" + name))


def opc(name):
    return GraphPath("OPCUAConnectivity", OPC_ROOT, (O + "has" + name,))


def engineering_query(*, projections=None, joins=(), where=None, **options):
    if projections is None:
        projections = (Projection("AssetIdentifier", dexpi("AssetIdentifier"),
                                  alias="dexpi"),)
    return SemanticQuery(
        question="Show engineering information",
        projections=tuple(projections),
        joins=tuple(joins), where=where,
        **options,
    ).validate(EngineeringSchema())


def test_e1_single_property_projection():
    sparql = compile_unified_graph_query(engineering_query())
    assert sparql.startswith("SELECT DISTINCT ?AssetIdentifier WHERE")
    assert "<" + D + "hasInstrumentationFunction>" in sparql
    assert "<" + D + "hasAssetIdentifier>" in sparql


def test_e1_multiple_properties_share_one_entity_root():
    plan = engineering_query(projections=(
        Projection("AssetIdentifier", dexpi("AssetIdentifier"), alias="dexpi"),
        Projection("ProductIdentifier", dexpi("ProductIdentifier"), alias="dexpi"),
    ))
    sparql = compile_unified_graph_query(plan)
    assert "SELECT DISTINCT ?AssetIdentifier ?ProductIdentifier" in sparql
    assert "?root_dexpi" in sparql
    assert "Cartesian" not in sparql


def test_e1_multi_hop_and_nonprojected_localid_filter():
    plan = engineering_query(where=Predicate(
        "LocalID", "eq", "FI_103", dexpi("LocalId"), "dexpi"))
    sparql = compile_unified_graph_query(plan)
    assert "<" + D + "hasInstrumentationFunction>" in sparql
    assert "<" + D + "hasLocalId>" in sparql
    assert 'FI_103' in sparql
    assert "SELECT DISTINCT ?AssetIdentifier" in sparql


def test_e1_nested_projected_filter():
    plan = engineering_query(where=BooleanExpression("and", (
        Predicate("AssetIdentifier", "exists"),
        Predicate("AssetIdentifier", "ne", "A-0"),
    )))
    sparql = compile_unified_graph_query(plan)
    assert "BOUND(" in sparql and '"A-0"' in sparql


def test_e1_cross_domain_join_uses_shacl_asset_paths():
    plan = engineering_query(
        projections=(Projection("SignalName", opc("SignalName"),
                                alias="opcuaconnectivity"),),
        joins=(Join("dexpi", "opcuaconnectivity",
                    dexpi("AssetIdentifier"), opc("AssetIdentifier")),),
        where=Predicate("LocalID", "eq", "FI_103", dexpi("LocalId"), "dexpi"),
    )
    sparql = compile_unified_graph_query(plan)
    assert "FILTER(?join_0_left_1 = ?join_0_right_0)" in sparql
    assert "?join_0_left_0 <" + D + "hasLocalId>" in sparql
    assert "SELECT DISTINCT ?SignalName" in sparql


def test_e1_unvalidated_or_invented_shacl_path_rejected():
    with pytest.raises(ValueError, match="SHACL"):
        engineering_query(projections=(
            Projection("Unknown", GraphPath("DEXPI", ROOT,
                       (D + "hasInventedProperty",)), alias="dexpi"),))
    raw = SemanticQuery("Show engineering information", (
        Projection("AssetIdentifier", dexpi("AssetIdentifier"), alias="dexpi"),))
    with pytest.raises(ValueError, match="validated"):
        compile_unified_graph_query(raw)


def test_e1_unsupported_grouping_and_aggregation_fail_closed():
    with pytest.raises(ValueError, match="Aggregation"):
        compile_unified_graph_query(engineering_query(
            aggregation="count", group_by=("AssetIdentifier",)))
    with pytest.raises(ValueError, match="Aggregation"):
        compile_unified_graph_query(engineering_query(group_by=("AssetIdentifier",)))


def test_e1_legacy_engineering_adapter_contract_is_unchanged(monkeypatch):
    """Baseline original route independently, without pretending IRs are equal."""
    calls = []
    class FakeSchema:
        def __init__(self, path):
            calls.append(("schema", str(path)))
    def planner(question, context, schema):
        calls.append(("planner", question))
        return {"query_type": "SELECT", "intent": "list"}
    def compiler(plan, schema, **kwargs):
        calls.append(("compiler", kwargs))
        return "SELECT ?entity WHERE { ?entity ?p ?o } LIMIT 100"
    def executor(endpoint, sparql):
        calls.append(("executor", endpoint))
        return [{"entity": "FI_103"}]
    monkeypatch.setattr(dtwise_query, "Schema", FakeSchema)
    monkeypatch.setattr(dtwise_query, "plan_question_semantic", planner)
    monkeypatch.setattr(dtwise_query, "compile_sparql", compiler)
    monkeypatch.setattr(dtwise_query, "execute_select", executor)
    monkeypatch.setattr(dtwise_query, "build_answer",
                        lambda bindings, plan, limit: {"rows": bindings})
    class SchemaPath:
        def is_file(self):
            return True
        def __str__(self):
            return "schema-index.json"
    monkeypatch.setattr(dtwise_query, "SCHEMA_PATH", SchemaPath())
    result = dtwise_query.run_question(
        "Show engineering identifiers",
        environ={"GRAPHDB_SPARQL_ENDPOINT": "http://graphdb.invalid/sparql"})
    assert result["mode"] == "frozen_dtwise_graphdb"
    assert result["executed"] is True
    assert result["answer"]["rows"] == [{"entity": "FI_103"}]
    assert [item[0] for item in calls] == [
        "schema", "planner", "compiler", "executor"]
    assert calls[2][1] == {"limit": 100, "graph_mode": "all_named"}
