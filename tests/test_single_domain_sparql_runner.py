"""Integration runner classification tests without Ollama or RDF execution."""
from types import SimpleNamespace

from benchmarks.shacl_phase1.run_single_domain_sparql import compile_entry

ROOT = "https://example.org/shape/Device"
CLASS = "https://example.org/ecad/Device"
SH_CLASS = "http://www.w3.org/ns/shacl#class"
ENTRY = {"id": "SD01-P1", "scenario_id": "SD01", "domain": "ecad",
         "query": "Show ECAD Devices."}


def test_missing_prior_result():
    result = compile_entry(ENTRY, None, None, {})
    assert result["status"] == "missing_phase1_result"


def test_rejects_question_mismatch():
    result = compile_entry(ENTRY, {"query": "Another question"}, None, {})
    assert result["status"] == "input_mismatch"


def test_reports_planning_failure():
    prior = {"query": ENTRY["query"], "record": {
        "status": "invalid_response", "validation_errors": ["bad projection"]}}
    result = compile_entry(ENTRY, prior, None, {})
    assert result["status"] == "planning_failed"


def test_rejects_old_record_without_registry():
    prior = {"query": ENTRY["query"], "pass": True,
             "record": {"status": "valid_response", "answer": {}}}
    result = compile_entry(ENTRY, prior, None, {})
    assert result["status"] == "missing_candidate_registry"


def test_compiles_validated_entity_record():
    index = SimpleNamespace(domain="ecad", shapes={ROOT: {}}, edges=[], properties={})
    schema = {"relationships": [
        {"domain": "ecad", "subject": ROOT, "predicate": SH_CLASS, "object": CLASS}]}
    prior = {"query": ENTRY["query"], "pass": True, "record": {
        "status": "valid_response", "validation_errors": [],
        "candidate_paths": [{"id": "R1", "kind": "result"}],
        "candidate_registry": {"R1": {"domain": "ecad", "kind": "result",
                                      "node_uris": [ROOT], "edges": []}},
        "answer": {"status": "selected", "projection_ids": ["R1"],
                   "existence_ids": [], "filters": [], "boolean_operator": "NONE",
                   "join": False, "join_owner_id": None,
                   "count_target_id": None, "order_by": [], "limit": None}}}
    result = compile_entry(ENTRY, prior, index, schema)
    assert result["status"] == "compiled"
    assert "<" + CLASS + ">" in result["sparql"]


def test_semantic_mismatch_not_compiled():
    prior = {"query": ENTRY["query"], "pass": False,
             "errors": ["projections"], "record": {"status": "valid_response"}}
    result = compile_entry(ENTRY, prior, None, {})
    assert result["status"] == "semantic_mismatch"
