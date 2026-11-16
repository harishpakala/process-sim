"""Offline contract tests for the first unified SHACL planner increment."""
import pytest

from process_sim.api.unified_query_plan import (
    QueryOperation, TemporalWindow, UnifiedQueryPlan,
    from_engineering_plan, from_historian_plan,
)

RUN = "11111111-2222-3333-4444-555555555555"
QUESTION = "Plot recorded measurements of DEXPI FI_101 for simulation run " + RUN


def test_historian_maps_to_one_validated_multisource_plan():
    legacy = {
        "domain": "DEXPI", "engineering_function": "FI_101", "run_id": RUN,
        "start_simulation_seconds": None, "end_simulation_seconds": None,
        "shacl_evidence": {"shape": "urn:dexpi:shape",
                           "properties": [{"property": "urn:localid", "evidence_ids": ["e1"]}]},
    }
    plan = from_historian_plan(QUESTION, legacy)
    assert [op.kind for op in plan.operations] == ["signal_resolution", "observations"]
    assert [op.source for op in plan.operations] == ["graphdb", "timescaledb"]
    assert plan.temporal.start_seconds is None
    assert plan.temporal.end_seconds is None
    assert plan.to_dict()["version"] == "unified-shacl-v1"


def test_engineering_maps_to_same_plan_contract():
    plan = from_engineering_plan("List DEXPI instrumentation functions", {
        "intent": "list", "evidence_ids": ["shacl-hop-1"],
    })
    assert plan.operations[0].kind == "graph_query"
    assert plan.operations[0].shacl_evidence["evidence_ids"] == ["shacl-hop-1"]


@pytest.mark.parametrize("start,end", [(-1, None), (200, 100), (float("inf"), None),
                                       (float("nan"), None)])
def test_invalid_time_window_fails_closed(start, end):
    with pytest.raises(ValueError):
        TemporalWindow(start, end)


def test_observations_cannot_skip_signal_resolution():
    with pytest.raises(ValueError):
        UnifiedQueryPlan(QUESTION, (QueryOperation("observations", "timescaledb"),))


def test_missing_shacl_evidence_is_rejected():
    with pytest.raises(ValueError):
        from_historian_plan(QUESTION, {
            "domain": "DEXPI", "engineering_function": "FI_101", "run_id": RUN,
            "shacl_evidence": {"properties": []},
        })
