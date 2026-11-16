"""Offline checks for experimental engineering CLI orchestration."""
from unittest.mock import patch

import pytest

from scripts.unified_question_experimental import run


def test_engineering_cli_reuses_shacl_planner_and_unified_executor():
    plan = {"query_type": "SELECT", "intent": "list", "evidence_ids": ["shape-1"]}
    execution = {
        "plan": {"operations": [{"kind": "graph_query"}]},
        "graph": {"sparql": "SELECT ?entity WHERE { ?entity ?p ?o }",
                  "answer": {"count": 1, "entities": ["urn:example"]}},
        "historian": None,
    }
    schema = object()
    with patch("scripts.unified_question_experimental.plan_question_semantic",
               return_value=plan) as planner, patch(
               "scripts.unified_question_experimental.execute_unified_plan",
               return_value=execution) as executor:
        result = run("List instrumentation functions in DEXPI", schema=schema,
                     environ={"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql"})
    assert result["status"] == "PASS"
    assert result["fully_unified_interpretation"] is False
    assert result["historian_executed"] is False
    assert result["answer"]["count"] == 1
    planner.assert_called_once_with("List instrumentation functions in DEXPI", [], schema)
    assert executor.call_args.args[0].operations[0].kind == "graph_query"


def test_cli_requires_graphdb_endpoint_before_planning():
    with pytest.raises(ValueError, match="GRAPHDB_SPARQL_ENDPOINT"):
        run("List instrumentation functions", schema=object(), environ={})


def test_cli_rejects_invalid_question():
    with pytest.raises(ValueError, match="Question"):
        run("x", schema=object(),
            environ={"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql"})


def test_cli_rejects_unexpected_historian_execution():
    with patch("scripts.unified_question_experimental.plan_question_semantic",
               return_value={"intent": "list"}), patch(
               "scripts.unified_question_experimental.execute_unified_plan",
               return_value={"historian": {"observationCount": 1}, "graph": {}}):
        with pytest.raises(RuntimeError, match="historian"):
            run("List instrumentation functions", schema=object(),
                environ={"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql"})
