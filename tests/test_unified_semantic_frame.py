"""Offline v3 semantic frame and unified plan tests."""
from unittest.mock import patch
import pytest

from process_sim.api.unified_semantic_frame import interpret_semantic_frame
from process_sim.api.unified_semantic_experimental import plan_unified_question_v3

RUN = "11111111-2222-3333-4444-555555555555"
QUESTION = f"Plot measurements for DEXPI FI_101 in run {RUN} between 100 and 300 seconds"
CATALOG = [{"domain": "DEXPI", "entity": "InstrumentationFunction"}]


def proposal(**updates):
    value = dict(intent="observations", domain="DEXPI", entity="InstrumentationFunction",
                 local_id="FI_101", run_id=RUN, start_seconds=100, end_seconds=300)
    value.update(updates)
    return value


@pytest.fixture(autouse=True)
def catalog():
    with patch("process_sim.api.unified_semantic_frame._schema_catalog", return_value=CATALOG):
        yield


def test_one_pass_frame_and_plan_without_legacy_parser():
    with patch("process_sim.api.unified_semantic_experimental._shacl_evidence",
               create=True) as ignored, \
         patch("process_sim.api.historian_nl_experimental._shacl_evidence",
               return_value={"shape": "urn:shape", "properties": [
                   {"property": "urn:localid", "evidence_ids": ["e1"]}]}), \
         patch("process_sim.api.unified_semantic_experimental.plan_historian_question",
               side_effect=AssertionError("legacy parser must not run")):
        result = plan_unified_question_v3(
            QUESTION, schema=object(), interpret_frame=lambda q, c: proposal())
    assert result.interpretation == "single_semantic_frame_v3"
    assert [op.kind for op in result.operations] == ["signal_resolution", "observations"]
    assert result.temporal.start_seconds == 100


@pytest.mark.parametrize("updates", [
    {"local_id": "FI_999"}, {"run_id": "99999999-2222-3333-4444-555555555555"},
    {"domain": "UNKNOWN"}, {"entity": "Imaginary"}, {"start_seconds": 400},
    {"intent": "sql"}, {"unexpected": "field"},
])
def test_invalid_model_frame_rejected(updates):
    with pytest.raises(ValueError):
        interpret_semantic_frame(QUESTION, object(), interpret=lambda q, c: proposal(**updates))


def test_selected_context_conflict_rejected():
    with pytest.raises(ValueError, match="disagree"):
        interpret_semantic_frame(QUESTION, object(),
                                 context={"engineering_function": "FI_102"},
                                 interpret=lambda q, c: proposal())


def test_mixed_question_not_silently_degraded():
    with pytest.raises(ValueError, match="Mixed"):
        plan_unified_question_v3(QUESTION, schema=object(),
                                 interpret_frame=lambda q, c: proposal(intent="mixed"))


def test_graph_frame_uses_existing_shacl_graph_planner():
    with patch("process_sim.api.unified_semantic_experimental.plan_question_semantic",
               return_value={"intent": "list", "evidence_ids": ["hop"]}) as graph:
        result = plan_unified_question_v3(
            "List DEXPI instrumentation functions", schema=object(),
            interpret_frame=lambda q, c: proposal(
                intent="graph_query", local_id=None, run_id=None,
                start_seconds=None, end_seconds=None))
    assert result.operations[0].kind == "graph_query"
    graph.assert_called_once()
