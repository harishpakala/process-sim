"""Offline regression checks for experimental shared intent routing."""
from unittest.mock import patch

import pytest

from process_sim.api.unified_nl_experimental import classify_intent, run_unified_experiment
from process_sim.api.historian_nl_experimental import plan_historian_question

RUN = "11111111-2222-3333-4444-555555555555"
CONTEXT = {"domain": "DEXPI", "engineering_function": "FI_101", "run_id": RUN}


def evidence(_schema, domain):
    return {"shape": f"urn:{domain}:shape", "properties": [{"property": "urn:LocalId", "evidence_ids": ["e1"]}]}


@pytest.mark.parametrize("question", [
    f"Get historian values for DEXPI FI_101 in run {RUN}.",
    f"Show historical readings of FI_101 for run {RUN}.",
    f"Plot FI_101 for simulation run {RUN}.",
    f"Chart the recorded measurements for FI_101 in run {RUN}.",
    f"How did FI_101 behave during run {RUN}?",
])
def test_paraphrases_share_historian_plan(question):
    assert classify_intent(question) == "historian_observations"
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        plan = plan_historian_question(question, schema=object(), context=CONTEXT)
    assert (plan["domain"], plan["engineering_function"], plan["run_id"]) == ("DEXPI", "FI_101", RUN)


def test_time_paraphrases():
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        plans = [plan_historian_question(
            f"Plot FI_101 from {interval} in run {RUN}.", schema=object(), context=CONTEXT)
            for interval in ("100 to 300 seconds", "100 through 300 seconds")]
    assert all(p["start_simulation_seconds"] == 100 and p["end_simulation_seconds"] == 300 for p in plans)


@pytest.mark.parametrize("question", [
    f"Plot FI_102 for run {RUN}.",
    f"Plot FI_101 for run 99999999-2222-3333-4444-555555555555.",
    f"Plot FI_101 between 300 and 100 seconds for run {RUN}.",
    f"Plot FI_101 after a while for run {RUN}.",
])
def test_conflicting_or_unsupported_question_rejected(question):
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        with pytest.raises(ValueError):
            plan_historian_question(question, schema=object(), context=CONTEXT)


def test_engineering_routes_to_existing_planner():
    question = "Which ECAD devices are connected to this component?"
    assert classify_intent(question) == "engineering_query"
    with patch("process_sim.api.unified_nl_experimental.run_engineering_question") as run:
        run.return_value = {"plan": {"intent": "list"}, "answer": {"rows": []}}
        output = run_unified_experiment(question)
    assert output["intent"] == "engineering_query"
    run.assert_called_once()


def test_historian_routes_to_existing_executor():
    question = f"Plot FI_101 during run {RUN}."
    with patch("process_sim.api.unified_nl_experimental.plan_historian_question") as plan, \
         patch("process_sim.api.unified_nl_experimental.run_historian_question") as run:
        plan.return_value = {"domain": "DEXPI", "engineering_function": "FI_101", "run_id": RUN,
                             "start_simulation_seconds": None, "end_simulation_seconds": None}
        run.return_value = {"observationCount": 2}
        output = run_unified_experiment(question, context=CONTEXT)
    assert output["intent"] == "historian_observations"
    assert output["result"]["observationCount"] == 2
    run.assert_called_once()
