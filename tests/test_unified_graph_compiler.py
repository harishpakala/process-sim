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


def test_unbound_join_fails_closed():
    path = GraphPath("DEXPI", "shape:instrument", (URI,))
    with pytest.raises(ValueError, match="alias-to-entity"):
        compile_unified_graph_query(query(joins=(Join("a", "b", path, path),)))


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
