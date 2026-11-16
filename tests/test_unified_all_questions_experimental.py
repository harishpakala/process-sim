"""Offline routing and safety tests for the shared-frame CLI."""
from unittest.mock import patch

import pytest

from scripts.unified_all_questions_experimental import run
from process_sim.api.unified_query_plan import (
    QueryOperation, UnifiedQueryPlan, TemporalWindow,
)

ENV = {"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql",
       "TEP_TIMESCALE_DSN": "postgresql://example.invalid/db"}
Q = "List DEXPI instrumentation functions"


def _plan(kinds):
    ops = tuple(QueryOperation(k, "timescaledb" if k == "observations" else "graphdb",
                               {"validated_engineering_plan": {"intent": "list"}}
                               if k == "graph_query" else {})
                for k in kinds)
    return UnifiedQueryPlan(question=Q, operations=ops,
                            temporal=TemporalWindow())


def _execute(kinds):
    return {"plan": {"operations": [{"kind": k} for k in kinds]},
            "graph": {"sparql": "SELECT ?x WHERE {}", "answer": []}
            if "graph_query" in kinds else None,
            "historian": {"observationCount": 2} if "observations" in kinds else None,
            "join_type": "shared_entity_context_no_row_join",
            "resolution_execution": {"graphdb_signal_resolution_queries": 1}}


@pytest.mark.parametrize("kinds", [
    ("graph_query",),
    ("signal_resolution", "observations"),
    ("graph_query", "signal_resolution", "observations"),
])
def test_single_cli_for_all_plan_kinds(kinds):
    with patch("scripts.unified_all_questions_experimental.plan_unified_question_v3",
               return_value=_plan(kinds)) as planner, patch(
               "scripts.unified_all_questions_experimental.execute_unified_plan",
               return_value=_execute(kinds)) as executor:
        result = run(Q, schema=object(), environ=ENV)
    assert result["status"] == "PASS"
    assert result["operation_kinds"] == kinds
    assert result["fully_unified_interpretation"] is False
    assert executor.call_args.kwargs["single_resolution"] == ("observations" in kinds)
    planner.assert_called_once()


def test_missing_graphdb_rejected_before_planning():
    with pytest.raises(ValueError, match="GRAPHDB_SPARQL_ENDPOINT"):
        run(Q, schema=object(), environ={})


def test_missing_timescale_rejected_before_execution():
    with patch("scripts.unified_all_questions_experimental.plan_unified_question_v3",
               return_value=_plan(("signal_resolution", "observations"))):
        with pytest.raises(ValueError, match="TEP_TIMESCALE_DSN"):
            run(Q, schema=object(),
                environ={"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql"})


def test_planning_failure_is_not_downgraded():
    with patch("scripts.unified_all_questions_experimental.plan_unified_question_v3",
               side_effect=ValueError("No SHACL path matches")):
        with patch("scripts.unified_all_questions_experimental.execute_unified_plan") as executor:
            with pytest.raises(ValueError, match="No SHACL path"):
                run(Q, schema=object(), environ=ENV)
            executor.assert_not_called()
