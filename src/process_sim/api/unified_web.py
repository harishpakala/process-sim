"""Shared HTTP adapter for the one-Qwen SHACL unified planner.

No legacy NL planner is invoked. Existing discovery and legacy endpoints remain.
"""
from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.unified_cli import run_unified_cli
from process_sim.dtwise.schema import Schema


def run_unified_web(payload, *, runner=run_unified_cli, schema_factory=Schema):
    if not isinstance(payload, dict) or set(payload) - {
        "question", "context", "signal_field"
    } or "question" not in payload:
        raise ValueError("Expected question and optional context/signal_field")
    question = payload["question"]
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    context = payload.get("context") or {}
    if not isinstance(context, dict) or set(context) - {
        "run_id", "start_seconds", "end_seconds"
    }:
        raise ValueError("Context supports run_id, start_seconds, end_seconds only")
    signal_field = payload.get("signal_field")
    if signal_field is not None and (not isinstance(signal_field, str)
                                      or not signal_field.isidentifier()):
        raise ValueError("Invalid signal_field")
    report = runner(question.strip(), schema=schema_factory(str(SCHEMA_PATH)),
                    context=context, signal_field=signal_field)
    return {"mode": "unified_qwen_shacl", **report}
