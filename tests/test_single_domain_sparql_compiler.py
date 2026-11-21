"""Unit tests for deterministic single-domain SPARQL compilation (no Ollama)."""
from types import SimpleNamespace

import pytest

from process_sim.dtwise.shacl_planner.sparql_compiler import (
    CompilationError, compile_single_domain,
)

ROOT = "https://example.org/shape/Device"
CLASS = "https://example.org/ecad/Device"
PRED = "https://example.org/ecad/hasDeviceType"
PSHAPE = "https://example.org/shape/DeviceType"
SH_CLASS = "http://www.w3.org/ns/shacl#class"


def fixture():
    index = SimpleNamespace(
        domain="ecad", shapes={ROOT: {}}, edges=[],
        properties={ROOT: [{"owner": ROOT, "predicate": PRED,
                            "property_shape": PSHAPE}]},
    )
    schema = {"relationships": [
        {"domain": "ecad", "subject": ROOT, "predicate": SH_CLASS, "object": CLASS}
    ]}
    record = {
        "status": "valid_response", "validation_errors": [],
        "candidate_paths": [
            {"id": "R1", "kind": "result"},
            {"id": "P1", "kind": "property"},
        ],
        "candidate_registry": {
            "R1": {"domain": "ecad", "kind": "result",
                   "node_uris": [ROOT], "edges": []},
            "P1": {"domain": "ecad", "kind": "property",
                   "node_uris": [ROOT], "edges": [],
                   "property": {"owner": ROOT, "predicate": PRED,
                                "property_shape": PSHAPE}},
        },
        "answer": {
            "status": "selected", "projection_ids": ["R1"],
            "existence_ids": [], "filters": [], "boolean_operator": "NONE",
            "join": False, "join_owner_id": None, "count_target_id": None,
            "order_by": [], "limit": None,
        },
    }
    return record, index, schema


def test_entity_projection_uses_grounded_class():
    record, index, schema = fixture()
    query = compile_single_domain(record, index, schema)
    assert "SELECT ?n0 WHERE" in query
    assert "<" + CLASS + ">" in query
    assert "LIMIT" not in query


def test_filter_sort_limit():
    record, index, schema = fixture()
    answer = record["answer"]
    answer["filters"] = [{"property_id": "P1", "operator": "=", "value": "Sensor"}]
    answer["order_by"] = [{"property_id": "P1", "direction": "DESC"}]
    answer["limit"] = 10
    query = compile_single_domain(record, index, schema)
    assert "<" + PRED + ">" in query
    assert 'FILTER ((?v_P1 = "Sensor"))' in query
    assert "ORDER BY DESC(?v_P1)" in query
    assert "LIMIT 10" in query


def test_literal_escaping():
    record, index, schema = fixture()
    record["answer"]["filters"] = [
        {"property_id": "P1", "operator": "=", "value": 'a"\\\\b'}
    ]
    query = compile_single_domain(record, index, schema)
    assert "FILTER" in query
    assert '\\"' in query


def test_rejects_unvalidated_plan():
    record, index, schema = fixture()
    record["status"] = "invalid_response"
    with pytest.raises(CompilationError):
        compile_single_domain(record, index, schema)


def test_rejects_missing_class_constraint():
    record, index, schema = fixture()
    schema["relationships"] = []
    with pytest.raises(CompilationError, match="class"):
        compile_single_domain(record, index, schema)


def test_rejects_hallucinated_predicate():
    record, index, schema = fixture()
    record["candidate_registry"]["P1"]["property"]["predicate"] = "https://evil.example/p"
    record["answer"]["projection_ids"] = ["P1"]
    with pytest.raises(CompilationError, match="Unverified property"):
        compile_single_domain(record, index, schema)


def test_property_projection():
    record, index, schema = fixture()
    record["answer"]["projection_ids"] = ["P1"]
    query = compile_single_domain(record, index, schema)
    assert "SELECT ?v_P1 WHERE" in query
    assert "<" + PRED + ">" in query


def test_nested_or_uses_union_and_keeps_sibling_paths_distinct():
    record, index, schema = fixture()
    left = "https://example.org/shape/Left"
    right = "https://example.org/shape/Right"
    edge_left = {"from": ROOT, "to": left,
                 "predicate": "https://example.org/hasLeft",
                 "property_shape": "https://example.org/ps/left"}
    edge_right = {"from": ROOT, "to": right,
                  "predicate": "https://example.org/hasRight",
                  "property_shape": "https://example.org/ps/right"}
    index.shapes.update({left: {}, right: {}})
    index.edges.extend([edge_left, edge_right])
    index.properties[left] = [{"owner": left, "predicate": PRED,
                               "property_shape": PSHAPE}]
    index.properties[right] = [{"owner": right, "predicate": PRED,
                                "property_shape": PSHAPE}]
    for cid, node, edge in [("P2", left, edge_left), ("P3", right, edge_right)]:
        record["candidate_paths"].append({"id": cid, "kind": "property"})
        record["candidate_registry"][cid] = {
            "domain": "ecad", "kind": "property",
            "node_uris": [ROOT, node], "edges": [edge],
            "property": {"owner": node, "predicate": PRED,
                         "property_shape": PSHAPE}}
    record["answer"]["filters"] = [
        {"property_id": "P2", "operator": "=", "value": "A"},
        {"property_id": "P3", "operator": "=", "value": "B"}]
    record["answer"]["boolean_operator"] = "OR"
    query = compile_single_domain(record, index, schema)
    assert " UNION " in query
    assert "<https://example.org/hasLeft>" in query
    assert "<https://example.org/hasRight>" in query
    assert "?n1" in query and "?n2" in query
    assert 'FILTER ((?v_P2 = "A"))' in query
    assert 'FILTER ((?v_P3 = "B"))' in query


def test_or_same_property_with_two_values():
    record, index, schema = fixture()
    record["answer"]["filters"] = [
        {"property_id": "P1", "operator": "=", "value": "EQ_101"},
        {"property_id": "P1", "operator": "=", "value": "EQ_102"}]
    record["answer"]["boolean_operator"] = "OR"
    query = compile_single_domain(record, index, schema)
    assert " UNION " in query
    assert '"EQ_101"' in query and '"EQ_102"' in query
