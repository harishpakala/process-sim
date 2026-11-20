"""Independent state transitions; model transport is not bypassed."""
import pytest

from process_sim.dtwise import experimental_shacl_planner_state_machine as sm
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


QUESTION = ("Show EndPoint Address and PLCEndPoint Address belonging to the same "
            "Device where Device LocalId = FI_101 and Device DeviceType = Sensor in ECAD")


def setup_stages(monkeypatch, calls, *, status="selected", question=QUESTION):
    qualified = {"prompt": {"question": question, "candidates": [
        {"kind": "property", "id": "P0", "path": "Address"}]}}
    plan = {"status": status, "filters": [
        {"value": "FI_101"}, {"value": "Sensor"}]}
    monkeypatch.setattr(sm, "qualify_candidates",
                        lambda *args: calls.append("qualify") or qualified)
    monkeypatch.setattr(sm, "_expected_paths", lambda q: ("P0", "P1"))
    monkeypatch.setattr(sm, "_filter_ids", lambda q: ("P2", "P3"))
    def model(prompt, **kwargs):
        calls.append("ollama")
        assert kwargs["transport"] is not None
        return "model-proposal"
    monkeypatch.setattr(sm, "ollama_select", model)
    def validate(raw, q):
        calls.append("validate")
        assert raw == "model-proposal"
        assert q is qualified
        return plan
    monkeypatch.setattr(sm, "validate_phase4_and_join_plan", validate)
    monkeypatch.setattr(sm, "compile_phase4_and_join_sparql",
                        lambda result: calls.append("compile") or "SELECT DISTINCT ?x WHERE {}")
    return qualified, plan


def test_selected_plan_runs_each_gate_in_order(monkeypatch):
    calls = []
    setup_stages(monkeypatch, calls)
    monkeypatch.setattr(
        __import__("process_sim.dtwise.experimental_shacl_query_intent",
                   fromlist=["validated_join_intent"]),
        "validated_join_intent",
        lambda plan, qualified: calls.append("intent") or {"boolean_operator": "and"},
    )
    result = sm.run_join_state_machine(type("Index", (), {"domain": "ecad"})(),
                                       {}, transport=object())
    assert calls == ["qualify", "ollama", "validate", "intent", "compile"]
    assert result["state"] == "compiled"
    assert result["state_trace"] == [
        "start", "qualified", "model_selected", "validated", "compiled"
    ]


def test_model_abstention_skips_compilation(monkeypatch):
    calls = []
    setup_stages(monkeypatch, calls, status="unresolved")
    result = sm.run_join_state_machine(type("Index", (), {"domain": "ecad"})(),
                                       {}, transport=object())
    assert calls == ["qualify", "ollama", "validate"]
    assert result["state"] == "abstained"
    assert result["sparql"] is None
    assert result["state_trace"] == [
        "start", "qualified", "model_selected", "validated", "abstained"
    ]


def test_unsupported_abstains_before_model(monkeypatch):
    calls = []
    setup_stages(monkeypatch, calls, question=QUESTION + " and Status = Active")
    result = sm.run_join_state_machine(type("Index", (), {"domain": "ecad"})(),
                                       {}, transport=object())
    assert calls == ["qualify"]
    assert result["state_trace"] == ["start", "qualified", "abstained"]


def test_validation_failure_never_compiles(monkeypatch):
    calls = []
    setup_stages(monkeypatch, calls)
    def reject(*args):
        calls.append("reject")
        raise SelectionContractError("Model fabricated a path")
    monkeypatch.setattr(sm, "validate_phase4_and_join_plan", reject)
    with pytest.raises(SelectionContractError, match="fabricated"):
        sm.run_join_state_machine(type("Index", (), {"domain": "ecad"})(),
                                  {}, transport=object())
    assert calls == ["qualify", "ollama", "reject"]


def test_invalid_state_transition_rejected():
    trace = [sm.PlannerState.START]
    with pytest.raises(SelectionContractError, match="Invalid planner state"):
        sm.transition(trace, sm.PlannerState.COMPILED)
