#!/usr/bin/env python3
"""Audit TEP NEXUS live benchmark summary without treating pipeline acceptance as an oracle.

Usage:
 python scripts/audit_tep_nexus_benchmark.py --summary reports/tep_nexus_benchmark_full_coverage_summary.json --output reports/tep_nexus_benchmark_audit.json
Optional independently obtained historian comparisons:
 python scripts/audit_tep_nexus_benchmark.py --summary ... --expected-csv oracle_expected.csv --actual-csv benchmark_observed.csv
CSV comparison keys: case_id,run_id,signal_id,simulation_time,value
Both CSVs must be independently produced. This script does not query databases.
"""
import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

FIELDS = ("case_id", "run_id", "signal_id", "simulation_time", "value")

def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        return [tuple(row[k] for k in FIELDS) for row in reader]

def compare_rows(expected, actual):
    # Multiset comparison catches duplicates as well as missing/extra observations.
    # String equality is deliberately exact; normalize CSV representations upstream
    # only if an independently documented serialization policy permits it.
    e, a = Counter(read_rows(expected)), Counter(read_rows(actual))
    missing, extra = e - a, a - e
    return {"expected_rows": sum(e.values()), "actual_rows": sum(a.values()),
            "exact_multiset_match": not missing and not extra,
            "missing_count": sum(missing.values()), "extra_count": sum(extra.values()),
            "missing_examples": [list(x) for x in list(missing.elements())[:10]],
            "extra_examples": [list(x) for x in list(extra.elements())[:10]]}

def percentile(values, p):
    s = sorted(values)
    if not s:
        return None
    i = (len(s)-1)*p
    lo, hi = math.floor(i), math.ceil(i)
    return round(s[lo] + (s[hi]-s[lo])*(i-lo), 3)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True, type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--expected-csv", type=Path)
    p.add_argument("--actual-csv", type=Path)
    args = p.parse_args()
    if bool(args.expected_csv) != bool(args.actual_csv):
        p.error("--expected-csv and --actual-csv must be supplied together")
    source = json.loads(args.summary.read_text(encoding="utf-8"))
    cases = source["cases"]
    elapsed = [float(c["elapsed_seconds"]) for c in cases]
    positive = [c for c in cases if c["expected"] == "complete"]
    negative = [c for c in cases if c["expected"] == "reject"]
    audit = {
        "source_scope": source.get("scope"),
        "reported": {"total": source.get("total"), "passed": source.get("passed"), "failed": source.get("failed")},
        "recomputed": {
            "cases": len(cases),
            "case_ids_unique": len({(c["id"], c.get("repeat", 1)) for c in cases}) == len(cases),
            "positive": len(positive), "negative": len(negative),
            "accepted_cases": sum(bool(c["passed"]) for c in cases),
            "positive_completed": sum(c.get("pipeline_status") == "COMPLETED" for c in positive),
            "negative_rejected": sum(c.get("pipeline_status") == "ERROR" for c in negative),
            "positive_repair_succeeded": sum(bool(c.get("repair_succeeded")) for c in positive),
            "initial_failed_checks": sum(int(c.get("original_failed_check_count", 0)) for c in cases)
        },
        "latency_seconds": {
            "case_count": len(elapsed), "total": round(sum(elapsed), 3),
            "mean": round(statistics.mean(elapsed), 3),
            "median": round(statistics.median(elapsed), 3),
            "p95": percentile(elapsed, .95), "min": min(elapsed), "max": max(elapsed),
            "positive_median": round(statistics.median(float(c["elapsed_seconds"]) for c in positive), 3),
            "negative_median": round(statistics.median(float(c["elapsed_seconds"]) for c in negative), 3)
        },
        "independent_sql_oracle": {"status": "NOT_RUN", "reason": "No independently generated expected and observed CSVs supplied"},
        "stage_latency": {"status": "NOT_AVAILABLE", "reason": "Summary contains only elapsed_seconds per case"},
        "interpretation": "Pipeline checks passed at limited scope; not independently verified provenance or historian correctness"
    }
    if args.expected_csv:
        audit["independent_sql_oracle"] = {"status": "COMPARED", **compare_rows(args.expected_csv, args.actual_csv)}
    result = json.dumps(audit, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    print(result, end="")

if __name__ == "__main__":
    main()
