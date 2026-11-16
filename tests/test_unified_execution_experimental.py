"""Offline tests for opt-in unified graph/historian orchestration."""
from unittest.mock import patch
import pytest

from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.api.unified_query_plan import (
    QueryOperation, TemporalWindow, UnifiedQueryPlan,
)

RUN = "11111111-2222-3333-4444-555555555555"
ENV = {"GRAPHDB_SPARQL_ENDPOINT": "http://example.invalid/sparql",
       "TEP_TIMESCALE_DSN": "postgres://example.invalid/test"}


def mixed():
    return UnifiedQueryPlan(
        question=f"Show FI_101 engineering and recorded measurements for run {RUN}",
        temporal=TemporalWindow(100, 300),
        operations=(
            QueryOperation("graph_query", "graphdb",
                           {"validated_engineering_plan": {"intent": "list"}},
                           {"evidence_ids": ["hop"]}),
            QueryOperation("signal_resolution", "graphdb",
                           {"domain": "DEXPI", "engineering_function": "FI_101"},
                           {"shape": "urn:shape", "properties": [{"property": "urn:localid"}]}),
            QueryOperation("observations", "timescaledb",
                           {"run_id": RUN, "start_simulation_seconds": 100,
                            "end_simulation_seconds": 300}),
        ),
    )


def test_mixed_executor_preserves_both_results_and_identity():
    with patch("process_sim.api.unified_execution_experimental.compile_sparql",
               return_value="SELECT * WHERE {}"), \
         patch("process_sim.api.unified_execution_experimental.build_answer",
               return_value={"rows": 1}):
        calls = []
        def historian(payload, *, environ):
            calls.append(payload)
            return {"evidence": {"observations": [1]}}
        result = execute_unified_plan(
            mixed(), object(), environ=ENV,
            graph_executor=lambda endpoint, sparql: [{"entity": "FI_101"}],
            historian_executor=historian)
    assert result["graph"]["answer"] == {"rows": 1}
    assert result["historian"]["evidence"]["observations"] == [1]
    assert result["join_type"] == "shared_entity_context_no_row_join"
    assert calls[0]["engineering_function"] == "FI_101"
    assert calls[0]["start_simulation_seconds"] == 100
    assert calls[0]["end_simulation_seconds"] == 300


def test_mismatched_observation_window_rejected_before_io():
    plan = mixed()
    bad = UnifiedQueryPlan(
        question=plan.question, temporal=plan.temporal,
        operations=plan.operations[:-1] + (
            QueryOperation("observations", "timescaledb",
                           {"run_id": RUN, "start_simulation_seconds": 0,
                            "end_simulation_seconds": 300}),))
    with patch("process_sim.api.unified_execution_experimental.compile_sparql",
               return_value="SELECT * WHERE {}"):
        with pytest.raises(ValueError, match="bounds disagree"):
            execute_unified_plan(bad, object(), environ=ENV,
                                 graph_executor=lambda *args: pytest.fail("unexpected I/O"))


def test_unexpected_operation_order_rejected():
    plan = mixed()
    bad = UnifiedQueryPlan(
        question=plan.question, temporal=plan.temporal,
        operations=(plan.operations[1], plan.operations[0], plan.operations[2]))
    with pytest.raises(ValueError, match="sequence"):
        execute_unified_plan(bad, object(), environ=ENV)
