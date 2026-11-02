"""TEP NEXUS benchmark harness for local read-only integration runs.

Runs the existing query planner as a subprocess for each fixture.
Produces a sanitized summary, not raw evidence or credentials.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def evaluate_case(case, report, returncode):
    expected = case["expected"]
    status = report.get("status")
    if expected == "reject":
        # A rejected question must fail before any evidence is retrieved.
        passed = returncode != 0 and status == "ERROR" and report.get("evidence") is None
        return passed, "expected_rejection" if passed else "rejection_not_enforced"
    if expected != "complete":
        raise ValueError("Unknown expected outcome")
    plan = report.get("validated_plan") or {}
    details = report.get("answer_validation_details") or {}
    passed = (returncode == 0 and status == "COMPLETED"
              and plan.get("engineering_function") == case["function"]
              and report.get("answer_validation") == "CHECKS_PASSED_LIMITED_SCOPE"
              and details.get("failed_checks") == [])
    return passed, "completed_validated" if passed else "execution_or_validation_failure"


def run_suite(cases, run_id, output_dir, model, planner, extra_args=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, case in enumerate(cases):
        case_id = case["id"]
        # File names come from numeric indices, never untrusted fixture identifiers.
        report_path = output_dir / f"case_{index:03d}.json"
        command = [sys.executable, str(planner), "--question", case["question"],
                   "--run-id", run_id, "--model", model, "--output", str(report_path)]
        command.extend(extra_args or [])
        started = time.monotonic()
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
        duration = round(time.monotonic() - started, 3)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            passed, classification = evaluate_case(case, report, proc.returncode)
        except (OSError, ValueError, json.JSONDecodeError):
            report = {}
            passed, classification = False, "missing_or_invalid_report"
        results.append({
            "id": case_id, "function": case["function"], "expected": case["expected"],
            "passed": passed, "classification": classification,
            "elapsed_seconds": duration,
            "pipeline_status": report.get("status"),
            "answer_validation": report.get("answer_validation"),
            "original_failed_check_count": len(
                (report.get("original_answer_validation_details") or {}).get("failed_checks", [])),
            "repair_succeeded": (report.get("answer_repair") or {}).get("repair_success", False),
        })
    return {"schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "operator_local_execution_not_independent_provenance_verification",
            "total": len(results), "passed": sum(x["passed"] for x in results),
            "failed": sum(not x["passed"] for x in results), "cases": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="tests/fixtures/tep_nexus_benchmark_cases.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--planner", default="scripts/tep_nexus_ollama_query_planner.py")
    parser.add_argument("--output-dir", default="reports/tep_nexus_benchmark_runs")
    parser.add_argument("--summary", default="reports/tep_nexus_benchmark_summary.json")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        parser.error("Fixtures must be a nonempty JSON array")
    ids = set()
    for case in cases:
        if (not isinstance(case, dict)
                or set(case) != {"id", "function", "question", "expected"}
                or not all(isinstance(case[k], str) and case[k] for k in case)
                or case["expected"] not in {"complete", "reject"}
                or case["id"] in ids):
            parser.error("Invalid or duplicate benchmark fixture")
        ids.add(case["id"])
    summary = run_suite(cases, args.run_id, args.output_dir, args.model, args.planner,
                        ["--mapping-discovery", args.mapping_discovery,
                         "--temporal-coverage", args.temporal_coverage])
    destination = Path(args.summary)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Benchmark: {summary['passed']}/{summary['total']} passed; summary: {destination}")
    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
