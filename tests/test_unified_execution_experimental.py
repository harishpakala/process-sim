"""Offline tests for opt-in unified graph/historian orchestration."""
from unittest.mock import patch
import pytest

from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.api.unified_query_plan import (
    QueryOperation, TemporalWindow, UnifiedQueryPlan, consolidate_graph_stage,
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


def test_logical_graph_stage_preserves_grounding_and_observation_identity():
    original = mixed()
    combined = consolidate_graph_stage(original)
    assert [op.kind for op in combined.operations] == ["graph_query", "observations"]
    assert combined.operations[0].parameters["signal_resolution"] == {
        "domain": "DEXPI", "engineering_function": "FI_101"}
    assert combined.operations[0].shacl_evidence["signal_resolution"]["shape"] == "urn:shape"
    assert combined.operations[1] == original.operations[2]


def test_logical_graph_stage_executes_with_explicit_backend_disclosure():
    combined = consolidate_graph_stage(mixed())
    with patch("process_sim.api.unified_execution_experimental.compile_sparql",
               return_value="SELECT * WHERE {}"), \
         patch("process_sim.api.unified_execution_experimental.build_answer",
               return_value={"rows": 1}):
        result = execute_unified_plan(
            combined, object(), environ=ENV,
            graph_executor=lambda endpoint, sparql: [{"entity": "FI_101"}],
            historian_executor=lambda payload, *, environ: {
                "engineeringFunction": payload["engineering_function"],
                "observations": [1]})
    assert result["historian"]["engineeringFunction"] == "FI_101"
    assert result["graph_stage"]["logical_consolidation"] is True
    assert result["graph_stage"]["single_sparql_request"] is False


def test_logical_graph_stage_rejects_missing_resolution_evidence():
    original = mixed()
    invalid = UnifiedQueryPlan(
        question=original.question, temporal=original.temporal,
        operations=(original.operations[0],
                    QueryOperation("signal_resolution", "graphdb",
                                   original.operations[1].parameters, {}),
                    original.operations[2]))
    with pytest.raises(ValueError, match="SHACL"):
        consolidate_graph_stage(invalid)


def test_single_resolution_reuses_live_signal_for_timescaledb_without_second_lookup():
    calls = []
    def mapping_executor(endpoint, sparql):
        calls.append(("graphdb_mapping", sparql))
        return [{"entity": "urn:FI_101", "assetIdentifier": "asset-101",
                 "signalName": "sensor-101"}]
    def sample_retriever(dsn, run_id, signal, start, end):
        calls.append(("timescaledb", signal, start, end))
        return [{"simulationTimeHours": 100 / 3600, "value": 42.0}]
    with patch("process_sim.api.unified_execution_experimental.compile_sparql",
               return_value="SELECT * WHERE {}"), \
         patch("process_sim.api.unified_execution_experimental.build_answer",
               return_value={"count": 0}):
        result = execute_unified_plan(
            consolidate_graph_stage(mixed()), object(), environ=ENV,
            single_resolution=True, mapping_executor=mapping_executor,
            sample_retriever=sample_retriever,
            graph_executor=lambda endpoint, sparql: [])
    assert [call[0] for call in calls] == ["graphdb_mapping", "timescaledb"]
    assert result["historian"]["mapping"]["entity"] == "urn:FI_101"
    assert result["historian"]["observationCount"] == 1
    assert result["resolution_execution"]["historian_re_resolved_signal"] is False
    assert result["resolution_execution"]["additional_engineering_query"] is True


def test_single_resolution_ambiguity_blocks_historian_io():
    def ambiguous(endpoint, sparql):
        return [{"entity": "urn:FI_101", "assetIdentifier": "asset-101",
                 "signalName": signal} for signal in ("sensor-a", "sensor-b")]
    with patch("process_sim.api.unified_execution_experimental.compile_sparql",
               return_value="SELECT * WHERE {}"), \
         patch("process_sim.api.unified_execution_experimental.build_answer",
               return_value={"count": 0}):
        with pytest.raises(ValueError, match="ambiguous"):
            execute_unified_plan(
                consolidate_graph_stage(mixed()), object(), environ=ENV,
                single_resolution=True, mapping_executor=ambiguous,
                sample_retriever=lambda *args: pytest.fail("Historian should not run"),
                graph_executor=lambda endpoint, sparql: [])


def test_single_resolution_rejects_legacy_executor_before_io():
    with pytest.raises(ValueError, match="legacy historian executor"):
        execute_unified_plan(
            consolidate_graph_stage(mixed()), object(), environ=ENV,
            single_resolution=True,
            historian_executor=lambda *args, **kwargs: None,
            graph_executor=lambda *args: pytest.fail("GraphDB should not run"))
