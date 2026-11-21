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
