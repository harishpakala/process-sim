"""Paired TEP NEXUS deterministic/LLM experiment with optional VTKG/direct comparison.

Run from repository root with live GraphDB, TimescaleDB, and Ollama.
The deterministic arm receives structured identifiers, unlike the LLM arm.
"""
import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_benchmark import evaluate_case
from tep_nexus_deterministic_baseline import run_case as run_deterministic
from tep_nexus_function_registry import load_supported_functions


def percentile(values, fraction):
    import math
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def stats(rows):
    values = [r["elapsed_seconds"] for r in rows]
    return {
        "n": len(values),
        "median_seconds": statistics.median(values) if values else None,
        "p95_seconds": percentile(values, .95),
        "passed": sum(bool(r["passed"]) for r in rows),
        "failed": sum(not r["passed"] for r in rows),
    }


def run_llm(case, args, report_path):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    command = [
        sys.executable, args.planner, "--question", case["question"],
        "--run-id", args.run_id, "--model", args.model,
        "--output", str(report_path), "--mapping-discovery", args.mapping_discovery,
        "--temporal-coverage", args.temporal_coverage,
        "--graphdb-url", args.graphdb_url, "--history-limit", str(args.history_limit),
    ]
    start = time.perf_counter()
    report = {}
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
        elapsed = time.perf_counter() - start
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            passed, classification = evaluate_case(case, report, proc.returncode)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            passed, classification = False, "missing_or_invalid_report"
            report = {"error": str(exc)}
        error = report.get("error") or (proc.stderr[-1500:] if proc.returncode else None)
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        passed, classification, error = False, "timeout", f"Timeout after {args.timeout}s"
    return {
        "id": case["id"], "function": case["function"], "expected": case["expected"],
        "arm": "llm", "passed": passed, "classification": classification,
        "elapsed_seconds": round(elapsed, 6),
        "stage_latency_seconds": report.get("stage_latency_seconds", {}),
        "answer_validation": report.get("answer_validation"),
        "original_failed_check_count": len(
            (report.get("original_answer_validation_details") or {}).get("failed_checks", [])),
        "repair_succeeded": (report.get("answer_repair") or {}).get("repair_success", False),
        "error": error,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fixtures", default="reports/tep_nexus_benchmark_full_coverage_cases.json")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--history-limit", type=int, default=1000)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--planner", default="scripts/tep_nexus_ollama_query_planner.py")
    p.add_argument("--output", default="reports/tep_nexus_paired_experiment.json")
    p.add_argument("--csv", default="reports/tep_nexus_paired_experiment.csv")
    p.add_argument("--case-reports", default="reports/tep_nexus_paired_llm_runs")
    p.add_argument("--vtkg-window", nargs=2, type=float, action="append",
                   metavar=("START_SECONDS", "END_SECONDS"))
    p.add_argument("--vtkg-repetitions", type=int, default=3)
    p.add_argument("--vtkg-warmups", type=int, default=1)
    a = p.parse_args()
    if a.repeats < 1 or a.timeout < 1 or a.history_limit < 1:
        p.error("repeats, timeout, and history-limit must be positive")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    cases = json.loads(Path(a.fixtures).read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases or len({c["id"] for c in cases}) != len(cases):
        p.error("Fixture must contain nonempty cases with unique IDs")
    for case in cases:
        if case.get("expected") not in ("complete", "reject") or not all(
            case.get(k) for k in ("id", "function", "question")
        ):
            p.error("Invalid fixture case")
    registry = load_supported_functions(a.mapping_discovery, a.temporal_coverage, a.run_id)
    rows = []
    for repeat in range(1, a.repeats + 1):
        for index, case in enumerate(cases):
            order = ("deterministic", "llm") if (repeat + index) % 2 == 0 else ("llm", "deterministic")
            for arm in order:
                if arm == "deterministic":
                    row = run_deterministic(
                        case, a.run_id, registry, a.graphdb_url, dsn, a.history_limit)
                    row["arm"] = arm
                else:
                    row = run_llm(
                        case, a, Path(a.case_reports) / f"case_{repeat:02d}_{index:03d}.json")
                row["repeat"] = repeat
                rows.append(row)
                print(
                    f"repeat={repeat} case={case['id']} arm={arm} "
                    f"passed={row['passed']} seconds={row['elapsed_seconds']:.3f}",
                    flush=True,
                )
    positive = {
        arm: [r for r in rows if r["arm"] == arm and r["expected"] == "complete"]
        for arm in ("deterministic", "llm")
    }
    negative = {
        arm: [r for r in rows if r["arm"] == arm and r["expected"] == "reject"]
        for arm in ("deterministic", "llm")
    }
    by_key = {(r["repeat"], r["id"], r["arm"]): r for r in rows}
    pairs = []
    for repeat in range(1, a.repeats + 1):
        for case in cases:
            d = by_key[(repeat, case["id"], "deterministic")]
            l = by_key[(repeat, case["id"], "llm")]
            pairs.append({
                "repeat": repeat, "id": case["id"], "expected": case["expected"],
                "deterministic_passed": d["passed"], "llm_passed": l["passed"],
                "deterministic_seconds": d["elapsed_seconds"],
                "llm_seconds": l["elapsed_seconds"],
                "difference_seconds": round(l["elapsed_seconds"] - d["elapsed_seconds"], 6),
            })
    valid_pairs = [
        x for x in pairs if x["expected"] == "complete"
        and x["deterministic_passed"] and x["llm_passed"]
    ]
    summary = {
        "deterministic_positive": stats(positive["deterministic"]),
        "llm_positive": stats(positive["llm"]),
        "deterministic_negative": stats(negative["deterministic"]),
        "llm_negative": stats(negative["llm"]),
        "successful_positive_pairs": len(valid_pairs),
        "paired_difference_seconds": stats([
            {"elapsed_seconds": x["difference_seconds"], "passed": True} for x in valid_pairs
        ]),
    }
    if valid_pairs:
        summary["median_positive_pair_ratio_llm_over_deterministic"] = statistics.median(
            x["llm_seconds"] / x["deterministic_seconds"] for x in valid_pairs
            if x["deterministic_seconds"] > 0
        )
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": a.run_id,
        "configuration": {
            "fixtures": a.fixtures, "repeats": a.repeats,
            "model": a.model, "history_limit": a.history_limit, "timeout": a.timeout,
        },
        "summary": summary, "cases": rows, "pairs": pairs,
        "limitations": [
            "Deterministic arm receives structured identifiers and parameters; LLM arm interprets natural language.",
            "Sequential paired runs do not guarantee an immutable historian snapshot.",
            "GraphDB mappings remain provisional; physical sensor binding is not independently verified.",
            "LLM subprocess startup is included, while deterministic arm runs in-process.",
            "Pair differences are descriptive, not proof of causal LLM overhead.",
        ],
    }
    if a.vtkg_window:
        from tep_nexus_baseline_comparison import compare
        report["vtkg_direct_comparison"] = compare(
            a.run_id, a.vtkg_window, dsn=dsn, graphdb_url=a.graphdb_url,
            limit=a.history_limit, warmups=a.vtkg_warmups,
            repetitions=a.vtkg_repetitions,
            mapping_discovery=a.mapping_discovery,
            temporal_coverage=a.temporal_coverage,
        )
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    csv_path = Path(a.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    print(json.dumps(summary, indent=2))
    print(f"Saved {output} and {csv_path}")
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
