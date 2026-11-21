"""SPARQL syntax validation tests; no Ollama and no triplestore."""
import pytest

pytest.importorskip("rdflib")

from benchmarks.shacl_phase1.validate_single_domain_sparql import validate_results
from process_sim.dtwise.shacl_planner.sparql_validator import validate_syntax


def test_valid_select():
    assert validate_syntax("SELECT ?s WHERE { ?s ?p ?o . }")["status"] == "syntax_valid"


def test_invalid_select():
    assert validate_syntax("SELECT WHERE {")["status"] == "syntax_failed"


def test_missing_query():
    assert validate_syntax(None)["status"] == "missing_query"


def test_runner_keeps_compilation_and_execution_distinct():
    results = validate_results([
        {"id": "SD01-P1", "scenario_id": "SD01", "domain": "ecad",
         "status": "compiled", "sparql": "SELECT ?s WHERE { ?s ?p ?o . }"},
        {"id": "SD01-P2", "status": "compilation_failed", "error": "unsupported"},
    ])
    assert [r["status"] for r in results] == ["syntax_valid", "not_compiled"]
    assert all(r["execution_status"] == "not_checked" for r in results)
    assert all(r["semantic_status"] == "not_checked" for r in results)


def test_runner_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_results([{"id": "X"}, {"id": "X"}])
