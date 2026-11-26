"""Isolated regression tests; no GraphDB, TimescaleDB or existing endpoints needed."""
from unittest.mock import patch
import pytest

from process_sim.api.historian_nl_experimental import plan_historian_question, run_historian_nl_experiment

RUN = "11111111-2222-3333-4444-555555555555"
QUESTION = (
    f"Get historian values for DEXPI InstrumentationFunction with LocalID FI_101 "
    f"for simulation run {RUN} between simulation seconds 100 and 300."
)


def evidence(_schema, domain):
    return {"shape": f"urn:{domain}:shape", "properties": [{"property": "urn:LocalId", "evidence_ids": ["e1", "e2"]}]}


def test_nl_plan_explicit_fields():
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        plan = plan_historian_question(QUESTION, schema=object())
    assert plan["domain"] == "DEXPI"
    assert plan["engineering_function"] == "FI_101"
    assert plan["run_id"] == RUN
    assert plan["start_simulation_seconds"] == 100
    assert plan["end_simulation_seconds"] == 300


@pytest.mark.parametrize("question", [
    QUESTION.replace("DEXPI ", ""),
    QUESTION.replace("FI_101", ""),
    QUESTION.replace(RUN, ""),
    QUESTION.replace("100 and 300", "300 and 100"),
    QUESTION.replace("between simulation seconds 100 and 300", "after a while"),
])
def test_ambiguous_or_unsupported_question_rejected(question):
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        with pytest.raises(ValueError):
            plan_historian_question(question, schema=object())


def test_existing_executor_reused_unchanged():
    with patch("process_sim.api.historian_nl_experimental.plan_historian_question") as plan, \
         patch("process_sim.api.historian_nl_experimental.run_historian_question") as executor:
        plan.return_value = {
            "domain": "DEXPI", "engineering_function": "FI_101",
            "run_id": RUN, "start_simulation_seconds": 100,
            "end_simulation_seconds": 300, "shacl_evidence": {"shape": "urn:shape"}
        }
        executor.return_value = {"observationCount": 2}
        output = run_historian_nl_experiment(QUESTION)
    assert output["result"]["observationCount"] == 2
    executor.assert_called_once()
    assert executor.call_args.args[0]["engineering_function"] == "FI_101"

def test_reported_historian_question():
    question = ("Get historian values for the DEXPI InstrumentationFunction with LocalID FI_101 "
                "for simulation run 077a3c31-44f4-4f3a-b06d-ad52b148fe10, "
                "between simulation seconds 100 and 300.")
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        plan = plan_historian_question(question, schema=object())
    assert plan["intent"] == "historian_observations"
    assert plan["engineering_function"] == "FI_101"
    assert plan["run_id"] == "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
    assert plan["start_simulation_seconds"] == 100
    assert plan["end_simulation_seconds"] == 300


@pytest.mark.parametrize("interval,expected", [
    ("between simulation seconds 100 and 300", (100, 300)),
    ("from 100 to 300 seconds", (100, 300)),
    ("between 100 and 300 seconds", (100, 300)),
    ("", (None, None)),
])
def test_optional_and_paraphrased_intervals(interval, expected):
    from process_sim.api.historian_nl_experimental import canonical_historian_question
    question = f"Plot recorded measurements for DEXPI InstrumentationFunction with LocalID FI_101 in simulation run {RUN} {interval}."
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence):
        plan = plan_historian_question(question, schema=object())
    assert (plan["start_simulation_seconds"], plan["end_simulation_seconds"]) == expected
    canonical = canonical_historian_question(plan)
    assert ("for all simulation times" in canonical) == (expected == (None, None))


def test_experimental_executor_receives_canonical_question():
    from process_sim.api.historian_nl_experimental import canonical_historian_question
    question = f"Plot FI_101 from 100 to 300 seconds in DEXPI simulation run {RUN}"
    with patch("process_sim.api.historian_nl_experimental._shacl_evidence", side_effect=evidence), \
         patch("process_sim.api.historian_nl_experimental.run_historian_question") as executor:
        executor.return_value = {"observationCount": 2}
        output = run_historian_nl_experiment(question)
    assert output["plan"]["start_simulation_seconds"] == 100
    assert executor.call_args.args[0]["question"] == canonical_historian_question(output["plan"])
