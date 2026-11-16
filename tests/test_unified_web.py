"""Shared unified Web adapter contract tests (no Ollama or DB required)."""
import pytest

from process_sim.api.unified_web import run_unified_web


def test_shared_web_adapter_passes_question_and_selected_context_once():
    calls = []
    def runner(question, **kwargs):
        calls.append((question, kwargs["context"], kwargs["signal_field"]))
        return {"answer": {"rows": [], "count": 0}, "executed": True}
    result = run_unified_web(
        {"question": "How did DEXPI InstrumentationFunction behave?",
         "context": {"run_id": "00000000-0000-0000-0000-000000000001"},
         "signal_field": "SignalName"},
        runner=runner, schema_factory=lambda path: object())
    assert result["mode"] == "unified_qwen_shacl"
    assert len(calls) == 1
    assert calls[0][1]["run_id"].endswith("0001")
    assert calls[0][2] == "SignalName"


@pytest.mark.parametrize("payload", [
    {"question": "short", "context": {"domain": "DEXPI"}},
    {"question": "Show AssetIdentifier", "signal_field": "bad field"},
    {"question": "Show AssetIdentifier", "unexpected": True},
    {"question": "x"},
])
def test_shared_web_adapter_rejects_invalid_requests(payload):
    with pytest.raises(ValueError):
        run_unified_web(payload, runner=lambda *a, **k: {},
                        schema_factory=lambda path: object())
