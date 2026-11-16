"""Offline tests for the transitional shared-schema planner."""
from unittest.mock import patch

import pytest

from process_sim.api.unified_semantic_experimental import plan_unified_question

RUN = "11111111-2222-3333-4444-555555555555"


def test_engineering_uses_shared_schema_and_typed_plan():
    schema = object()
    with patch("process_sim.api.unified_semantic_experimental.plan_question_semantic") as planner:
        planner.return_value = {"intent": "list", "evidence_ids": ["hop-1"]}
        result = plan_unified_question("List DEXPI instrumentation functions", schema=schema)
    planner.assert_called_once_with("List DEXPI instrumentation functions", [], schema)
    assert result.operations[0].kind == "graph_query"
    assert result.operations[0].shacl_evidence["evidence_ids"] == ["hop-1"]
    assert result.interpretation == "shared_schema_transitional_v1"


def test_historian_uses_same_schema_and_typed_plan():
    schema = object()
    question = f"Plot recorded measurements for DEXPI FI_101 in simulation run {RUN}"
    with patch("process_sim.api.unified_semantic_experimental.plan_historian_question") as planner:
        planner.return_value = {
            "domain": "DEXPI", "engineering_function": "FI_101", "run_id": RUN,
            "start_simulation_seconds": 100, "end_simulation_seconds": 300,
            "shacl_evidence": {"shape": "urn:shape", "properties": [
                {"property": "urn:localid", "evidence_ids": ["e1"]}]},
        }
        result = plan_unified_question(question, schema=schema)
    planner.assert_called_once_with(question, schema=schema, context=None)
    assert [op.kind for op in result.operations] == ["signal_resolution", "observations"]
    assert result.temporal.start_seconds == 100


def test_mixed_question_fails_closed_instead_of_dropping_graph_request():
    with pytest.raises(ValueError, match="Mixed graph"):
        plan_unified_question(
            f"Which equipment is associated with FI_101 and plot recorded measurements for run {RUN}?",
            schema=object(),
        )


def test_temporal_without_observation_intent_fails_closed():
    with pytest.raises(ValueError, match="Temporal question"):
        plan_unified_question(f"Explain FI_101 during the run {RUN}", schema=object())


def test_context_does_not_force_historian():
    with patch("process_sim.api.unified_semantic_experimental.plan_question_semantic") as planner:
        planner.return_value = {"intent": "list"}
        result = plan_unified_question(
            "List DEXPI instrumentation functions",
            context={"domain": "DEXPI", "run_id": RUN}, schema=object(),
        )
    assert result.operations[0].kind == "graph_query"
