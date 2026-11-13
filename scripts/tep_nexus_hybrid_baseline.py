"""TEP NEXUS hybrid: LLM plans; validated GraphDB/TimescaleDB evidence;
deterministic answer generation and validation. No LLM answer generation.

Run from repository root. Read-only; provisional mappings are not physical verification.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_answer_repair import repair_answer
from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_ollama_query_planner import (
    build_evidence, plan_question, validate_plan,
)
from tep_nexus_semantic_temporal_live import retrieve_temporal_context


def run_hybrid(question, run_id, model, ollama_url, graphdb_url, dsn,
               mapping_discovery, temporal_coverage, history_limit):
    started = time.perf_counter()
    previous = started
    stages = {}

    def mark(name):
        nonlocal previous
        now = time.perf_counter()
        stages[name] = round(now - previous, 6)
        previous = now

    report = {
        "interface": "TEP NEXUS hybrid LLM planning deterministic answer",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": question, "model": model, "status": "STARTED",
        "raw_plan": None, "validated_plan": None, "evidence": None,
        "answer": None, "answer_validation": "NOT_AUTOMATICALLY_VERIFIED",
        "stage_latency_seconds": stages,
    }
    try:
        registry = load_supported_functions(mapping_discovery, temporal_coverage, run_id)
        mark("registry_load")
        raw_plan = plan_question(ollama_url, model, question, registry)
        report["raw_plan"] = raw_plan
        mark("llm_planning")
        plan = validate_plan(raw_plan, question, registry)
        report["validated_plan"] = plan
        mark("plan_validation")
        mapping = resolve_supported_mapping(graphdb_url, plan["engineering_function"], registry)
        if mapping["engineering_function"] != plan["engineering_function"]:
            raise RuntimeError("Resolved engineering function differs from plan")
        mark("graphdb_mapping_resolution")
        temporal = retrieve_temporal_context(
            dsn, run_id, mapping["operational_signal"],
            plan["history_window_minutes"], history_limit,
        )
        mark("timescaledb_retrieval")
        evidence = build_evidence(plan, mapping, temporal)
        report["evidence"] = evidence
        mark("evidence_construction")
        constructed = repair_answer(None, evidence)
        report["answer"] = constructed["repaired_answer"]
        validation = constructed["repaired_validation"]
        report["answer_validation_details"] = validation
        report["answer_validation"] = validation["status"]
        mark("deterministic_answer_and_validation")
        if not constructed["repair_success"] or validation.get("failed_checks"):
            raise RuntimeError("Deterministic answer failed validation")
        report["status"] = "COMPLETED"
    except Exception as exc:
        mark("failed_stage_partial")
        report["status"] = "ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--question", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--history-limit", type=int, default=1000)
    p.add_argument("--output", default="reports/tep_nexus_hybrid_query.json")
    a = p.parse_args()
    if a.history_limit < 1:
        p.error("--history-limit must be positive")
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    report = run_hybrid(
        a.question, a.run_id, a.model, a.ollama_url, a.graphdb_url,
        dsn, a.mapping_discovery, a.temporal_coverage, a.history_limit,
    )
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"status={report['status']} seconds={report['elapsed_seconds']:.3f} saved={output}")
    if report["status"] != "COMPLETED":
        print(report.get("error"), file=sys.stderr)
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
