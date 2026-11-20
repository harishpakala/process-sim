"""Stage-transition and fail-closed tests for migrated single-domain modes."""
import pytest

from process_sim.dtwise import experimental_shacl_planner_state_machine as sm
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


@pytest.mark.parametrize("operation,question", [
    ("phase2-filter", "Show Address where Device LocalId = FI_101 and DeviceType = Sensor"),
    ("phase3-and", "Show Address where Device LocalId = FI_101 or DeviceType = Sensor"),
    ("phase4-join", "Show Address in ECAD"),
    ("phase4-filtered-join", "Show Address in ECAD"),
])
def test_unsupported_abstains_before_model(monkeypatch, operation, question):
    qualified = {"prompt": {"question": question, "candidates": []}, "registry": {}}
    monkeypatch.setattr(sm, "qualify_candidates", lambda *_: qualified)
    monkeypatch.setattr(sm, "ollama_select", lambda *_a, **_kw: pytest.fail("Model called"))
    machine = sm.FilterAndJoinStateMachine(
        type("Index", (), {"domain": "ecad"})(), {}, operation=operation,
    )
    result = machine.run()
    assert result["plan"]["status"] == "unresolved"
    assert result["state_trace"] == ["start", "qualified", "abstained"]
    assert not result.get("sparql")
    assert not result.get("queries")


@pytest.mark.parametrize("operation", sm.FilterAndJoinStateMachine.OPERATIONS)
def test_invalid_stage_order_rejected(operation):
    machine = sm.FilterAndJoinStateMachine(
        type("Index", (), {"domain": "ecad"})(), {}, operation=operation,
    )
    with pytest.raises(SelectionContractError, match="Expected planner state"):
        machine.select_with_ollama()
    with pytest.raises(SelectionContractError, match="Expected planner state"):
        machine.validate()
    with pytest.raises(SelectionContractError, match="Expected planner state"):
        machine.compile()


def test_dispatch_rejects_unknown_operation():
    with pytest.raises(ValueError, match="Unsupported state-machine operation"):
        sm.run_single_domain_state_machine(
            type("Index", (), {"domain": "ecad"})(), {}, operation="cross-domain",
        )
