"""State-machine transition contract; live Ollama remains integration-tested."""
import pytest

from process_sim.dtwise import experimental_shacl_planner_state_machine as sm
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def test_selected_plan_compiles_after_validation(monkeypatch):
    calls = []

    def planner(index, prepared, **kwargs):
        calls.append(("planner", kwargs["transport"]))
        return {"plan": {"status": "selected"}, "qualified": {}}

    def compiler(result):
        calls.append(("compiler", None))
        return "SELECT DISTINCT ?x WHERE { ?x ?p ?o . }"

    monkeypatch.setattr(sm, "run_phase4_and_join_plan", planner)
    monkeypatch.setattr(sm, "compile_phase4_and_join_sparql", compiler)
    transport = object()
    result = sm.run_join_state_machine(None, None, transport=transport)
    assert calls == [("planner", transport), ("compiler", None)]
    assert result["state"] == "compiled"
    assert result["state_trace"] == [
        "start", "qualified", "model_selected", "validated", "compiled"
    ]


def test_unresolved_plan_abstains_without_compilation(monkeypatch):
    monkeypatch.setattr(
        sm, "run_phase4_and_join_plan",
        lambda *args, **kwargs: {"plan": {"status": "unresolved"}},
    )
    monkeypatch.setattr(
        sm, "compile_phase4_and_join_sparql",
        lambda *args: pytest.fail("Must not compile unresolved plan"),
    )
    result = sm.run_join_state_machine(None, None)
    assert result["state"] == "abstained"
    assert result["sparql"] is None
    assert result["state_trace"] == ["start", "qualified", "abstained"]


def test_invalid_state_transition_rejected():
    trace = [sm.PlannerState.START]
    with pytest.raises(SelectionContractError, match="Invalid planner state"):
        sm.transition(trace, sm.PlannerState.COMPILED)
