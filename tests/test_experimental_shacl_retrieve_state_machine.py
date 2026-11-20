"""RETRIEVE state machine parity tests; no CLI routing until live verification."""
import pytest

from process_sim.dtwise import experimental_shacl_planner_state_machine as sm
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def test_retrieve_state_order_and_selected_compilation(monkeypatch):
    calls = []
    qualified = {"prompt": {"question": "Show Address in ECAD", "candidates": [
        {"kind": "property", "id": "P1", "domain": "ecad", "path": "ECAD → Address",
         "property_name": "Address"}]},
        "registry": {"P1": {"node_uris": ["urn:root", "urn:owner"]}}}
    monkeypatch.setattr(sm, "qualify_candidates", lambda *_: calls.append("qualify") or qualified)
    monkeypatch.setattr(sm, "ollama_select", lambda *args, **kw: calls.append("ollama") or {"status": "selected"})
    import process_sim.dtwise.experimental_shacl_selection as selection
    monkeypatch.setattr(selection, "validate_selection",
                        lambda raw, offered: calls.append("validate") or {
                            "status": "selected", "selected_candidate_ids": ["P1"], "reason": "ok"})
    import process_sim.dtwise.experimental_shacl_phase1_ollama as phase1
    monkeypatch.setattr(phase1, "compile_phase1_sparql",
                        lambda result: calls.append("compile") or [
                            {"candidate_id": "P1", "sparql": "SELECT DISTINCT ?x WHERE {}"}])
    result = sm.run_retrieve_state_machine(type("Index", (), {"domain": "ecad"})(), {})
    assert calls == ["qualify", "ollama", "validate", "compile"]
    assert result["state_trace"] == ["start", "qualified", "model_selected", "validated", "compiled"]
    assert result["plan"]["selected_candidate_ids"] == ["P1"]


def test_retrieve_unsupported_skips_model(monkeypatch):
    qualified = {"prompt": {"question": 'Find Device where LocalId = "FI_101"',
                            "candidates": [{"kind": "property", "id": "P1"}]},
                 "registry": {"P1": {}}}
    monkeypatch.setattr(sm, "qualify_candidates", lambda *_: qualified)
    monkeypatch.setattr(sm, "ollama_select", lambda *_a, **_k: pytest.fail("Must abstain"))
    result = sm.run_retrieve_state_machine(type("Index", (), {"domain": "ecad"})(), {})
    assert result["state_trace"] == ["start", "qualified", "abstained"]
    assert result["queries"] == []


def test_retrieve_rejects_out_of_order_states():
    machine = sm.RetrievePlannerStateMachine(type("Index", (), {"domain": "ecad"})(), {})
    with pytest.raises(SelectionContractError, match="Expected planner state"):
        machine.validate()
    with pytest.raises(SelectionContractError, match="Expected planner state"):
        machine.compile()
