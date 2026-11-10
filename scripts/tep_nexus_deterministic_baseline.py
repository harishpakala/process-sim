"""Deterministic-only TEP NEXUS benchmark (no Ollama calls).

Structured fixture requests are the input: this is NOT a natural-language
understanding baseline. Live GraphDB and TimescaleDB services are required.
"""
import argparse
import csv
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_answer_repair import repair_answer
from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_ollama_query_planner import build_evidence, validate_plan
from tep_nexus_semantic_temporal_live import retrieve_temporal_context


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(__import__("math").ceil(len(ordered) * fraction)) - 1))]


def run_case(case, run_id, registry, graphdb_url, dsn, history_limit):
    started = time.perf_counter()
    stages = {}
    previous = started

    def mark(name):
        nonlocal previous
        now = time.perf_counter()
        stages[name] = round(now - previous, 6)
        previous = now

    result = {"id": case["id"], "function": case["function"],
              "expected": case["expected"], "status": "STARTED",
              "stage_latency_seconds": stages, "answer_validation": None}
    try:
        # Fixture supplies the function and request parameters, not an LLM.
        # Validate against identifiers in the original question to preserve
        # the benchmark's conflicting-identifier negative case.
        plan = validate_plan({
            "intent": "latest_and_history",
            "engineering_function": case["function"],
            "history_window_minutes": 10,
            "include_asset": True,
            "include_provenance": True,
        }, case["question"], registry)
        mark("structured_request_validation")
        mapping = resolve_supported_mapping(graphdb_url, plan["engineering_function"], registry)
        if mapping["engineering_function"] != plan["engineering_function"]:
            raise RuntimeError("Resolved engineering function differs from request")
        mark("graphdb_mapping_resolution")
        temporal = retrieve_temporal_context(
            dsn, run_id, mapping["operational_signal"],
            plan["history_window_minutes"], history_limit)
        mark("timescaledb_retrieval")
        evidence = build_evidence(plan, mapping, temporal)
        mark("evidence_construction")
        repaired = repair_answer(None, evidence)
        mark("deterministic_answer_and_validation")
        result["answer_validation"] = repaired["repaired_validation"]["status"]
        result["status"] = "COMPLETED"
        result["observation_signal"] = evidence["operational_signal"]
        result["sample_count"] = (evidence.get("history") or {}).get("sample_count")
        result["passed"] = (
            case["expected"] == "complete" and repaired["repair_success"]
            and evidence["engineering_function"] == case["function"])
        result["classification"] = "completed_validated" if result["passed"] else "unexpected_completion"
    except Exception as exc:
        mark("failed_stage_partial")
        error = f"{type(exc).__name__}: {exc}"
        result["status"] = "ERROR"
        result["error"] = error
        result["passed"] = (
            case["expected"] == "reject"
            and (not case.get("expected_error") or case["expected_error"] in error))
        result["classification"] = "expected_rejection" if result["passed"] else "unexpected_error"
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fixtures", default="tests/fixtures/tep_nexus_benchmark_cases.json")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--history-limit", type=int, default=1000)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--output", default="reports/deterministic_baseline_results.json")
    p.add_argument("--csv", default="reports/deterministic_baseline_cases.csv")
    a = p.parse_args()
    if a.repeats < 1 or a.history_limit < 1:
        p.error("--repeats and --history-limit must be positive")
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN must be set")
    cases = json.loads(Path(a.fixtures).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases or any(
        not isinstance(c, dict) or
        not all(isinstance(c.get(k), str) and c[k] for k in ("id", "function", "question", "expected"))
        or c["expected"] not in ("complete", "reject") for c in cases
    ):
        p.error("Invalid fixture cases")
    registry = load_supported_functions(a.mapping_discovery, a.temporal_coverage, a.run_id)
    results = []
    for repeat in range(1, a.repeats + 1):
        for case in cases:
            row = run_case(case, a.run_id, registry, a.graphdb_url, dsn, a.history_limit)
            row["repeat"] = repeat
            results.append(row)
    elapsed = [r["elapsed_seconds"] for r in results]
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "deterministic_structured_request_no_llm",
        "run_id": a.run_id,
        "configuration": {"fixtures": a.fixtures, "repeats": a.repeats,
                          "history_limit": a.history_limit},
        "summary": {
            "total": len(results), "passed": sum(r["passed"] for r in results),
            "failed": sum(not r["passed"] for r in results),
            "median_seconds": statistics.median(elapsed),
            "p95_seconds": percentile(elapsed, .95),
        },
        "limitations": [
            "Function identifiers and request parameters come from fixtures; natural-language planning is not evaluated.",
            "Engineering mappings are provisional; shared historian data does not verify physical sensor identity.",
            "Sequential live queries may observe different database states than historical LLM benchmark runs.",
            "This script measures no VTKG construction; it uses the existing GraphDB-to-TimescaleDB evidence path.",
        ],
        "cases": results,
    }
    out, csv_path = Path(a.output), Path(a.csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    fields = ["id", "repeat", "function", "expected", "passed", "classification",
              "status", "elapsed_seconds", "answer_validation", "observation_signal", "sample_count", "error"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(0 if report["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
