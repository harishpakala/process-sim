"""Three-arm paired TEP NEXUS benchmark: structured deterministic, hybrid, full LLM.

Runs from repository root. Each fixture is evaluated in all three arms per
repeat with rotating order. Saves a checkpoint after each case; Ctrl+C keeps
completed results. LLM and hybrid both run as subprocesses.
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
from tep_nexus_paired_experiment import percentile


ARMS = ("deterministic", "hybrid", "llm")


def stats(rows):
    values = [r["elapsed_seconds"] for r in rows]
    return {
        "n": len(rows), "passed": sum(bool(r["passed"]) for r in rows),
        "failed": sum(not r["passed"] for r in rows),
        "median_seconds": statistics.median(values) if values else None,
        "p95_seconds": percentile(values, .95),
    }


def subprocess_arm(arm, case, args, report_path):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    script = args.hybrid_script if arm == "hybrid" else args.llm_script
    command = [
        sys.executable, script, "--question", case["question"],
        "--run-id", args.run_id, "--model", args.model,
        "--output", str(report_path), "--mapping-discovery", args.mapping_discovery,
        "--temporal-coverage", args.temporal_coverage,
        "--graphdb-url", args.graphdb_url, "--history-limit", str(args.history_limit),
        "--ollama-url", args.ollama_url,
    ]
    started = time.perf_counter()
    report, error = {}, None
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            passed, classification = evaluate_case(case, report, proc.returncode)
        except (OSError, ValueError) as exc:
            passed, classification = False, "missing_or_invalid_report"
            error = str(exc)
        if proc.returncode and not error:
            error = report.get("error") or proc.stderr[-1000:]
    except subprocess.TimeoutExpired:
        passed, classification = False, "timeout"
        error = f"Timeout after {args.timeout}s"
    return {
        "id": case["id"], "function": case["function"], "expected": case["expected"],
        "arm": arm, "passed": passed, "classification": classification,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "stage_latency_seconds": report.get("stage_latency_seconds", {}),
        "answer_validation": report.get("answer_validation"),
        "original_failed_check_count": len(
            (report.get("original_answer_validation_details") or {}).get("failed_checks", [])),
        "error": error,
    }


def save(args, rows, cases):
    summary = {
        arm: {
            "positive": stats([r for r in rows if r["arm"] == arm and r["expected"] == "complete"]),
            "negative": stats([r for r in rows if r["arm"] == arm and r["expected"] == "reject"]),
        } for arm in ARMS
    }
    indexed = {(r["repeat"], r["id"], r["arm"]): r for r in rows}
    pairs = []
    for repeat in range(1, args.repeats + 1):
        for case in cases:
            triple = [indexed.get((repeat, case["id"], arm)) for arm in ARMS]
            if not all(triple):
                continue
            d, h, l = triple
            pairs.append({
                "repeat": repeat, "id": case["id"], "expected": case["expected"],
                "deterministic_seconds": d["elapsed_seconds"],
                "hybrid_seconds": h["elapsed_seconds"],
                "llm_seconds": l["elapsed_seconds"],
                "deterministic_passed": d["passed"],
                "hybrid_passed": h["passed"], "llm_passed": l["passed"],
                "llm_minus_hybrid_seconds": round(l["elapsed_seconds"] - h["elapsed_seconds"], 6),
            })
    valid = [p for p in pairs if p["expected"] == "complete"
             and p["deterministic_passed"] and p["hybrid_passed"] and p["llm_passed"]]
    summary["successful_positive_triples"] = len(valid)
    if valid:
        summary["median_llm_minus_hybrid_seconds"] = statistics.median(
            p["llm_minus_hybrid_seconds"] for p in valid)
        summary["median_llm_over_hybrid_ratio"] = statistics.median(
            p["llm_seconds"] / p["hybrid_seconds"] for p in valid
            if p["hybrid_seconds"] > 0)
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "configuration": {"fixtures": args.fixtures, "repeats": args.repeats,
                          "model": args.model, "timeout": args.timeout},
        "summary": summary, "cases": rows, "triples": pairs,
        "limitations": [
            "Deterministic arm uses structured fixture identifiers; hybrid and full LLM interpret natural language.",
            "LLM and hybrid subprocess startup is included; deterministic arm executes in-process.",
            "Sequential measurements do not guarantee a common immutable historian snapshot.",
            "Mappings are provisional and not physically verified.",
            "Final LLM validity may depend on deterministic repair; inspect original_failed_check_count.",
            "Paired differences are descriptive and do not isolate model-inference overhead.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    path = Path(args.csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if pairs:
            writer = csv.DictWriter(f, fieldnames=list(pairs[0]))
            writer.writeheader()
            writer.writerows(pairs)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fixtures", default="reports/tep_nexus_benchmark_full_coverage_cases.json")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--history-limit", type=int, default=1000)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--hybrid-script", default="scripts/tep_nexus_hybrid_baseline.py")
    p.add_argument("--llm-script", default="scripts/tep_nexus_ollama_query_planner.py")
    p.add_argument("--output", default="reports/tep_nexus_three_arm_experiment.json")
    p.add_argument("--csv", default="reports/tep_nexus_three_arm_experiment.csv")
    p.add_argument("--case-reports", default="reports/tep_nexus_three_arm_runs")
    a = p.parse_args()
    if min(a.repeats, a.timeout, a.history_limit) < 1:
        p.error("repeats, timeout, and history-limit must be positive")
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    cases = json.loads(Path(a.fixtures).read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        p.error("Fixtures must be a nonempty JSON array")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not all(
            isinstance(case.get(k), str) and case[k]
            for k in ("id", "function", "question", "expected")
        ) or case["expected"] not in ("complete", "reject") or case["id"] in ids:
            p.error("Invalid or duplicate fixture")
        ids.add(case["id"])
    registry = load_supported_functions(a.mapping_discovery, a.temporal_coverage, a.run_id)
    rows = []
    try:
        for repeat in range(1, a.repeats + 1):
            for index, case in enumerate(cases):
                offset = (repeat + index) % len(ARMS)
                order = ARMS[offset:] + ARMS[:offset]
                for arm in order:
                    if arm == "deterministic":
                        row = run_deterministic(
                            case, a.run_id, registry, a.graphdb_url, dsn, a.history_limit)
                        row["arm"] = arm
                    else:
                        row = subprocess_arm(
                            arm, case, a,
                            Path(a.case_reports) / f"{arm}_{repeat:02d}_{index:03d}.json")
                    row["repeat"] = repeat
                    rows.append(row)
                    print(f"repeat={repeat} case={case['id']} arm={arm} "
                          f"passed={row['passed']} seconds={row['elapsed_seconds']:.3f}", flush=True)
                save(a, rows, cases)
    except KeyboardInterrupt:
        save(a, rows, cases)
        print("Interrupted: completed-case checkpoint saved.", file=sys.stderr)
        return 130
    summary = save(a, rows, cases)
    print(json.dumps(summary, indent=2))
    print(f"Saved {a.output} and {a.csv}")
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
