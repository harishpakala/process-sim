"""Repeated, read-only VTKG latency benchmark with auditable JSON and CSV.

Each repetition calls the existing structural evaluator; warmup measurements
are discarded. Percentiles use nearest-rank empirical order statistics.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_semantic_temporal_evaluation import evaluate


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def benchmark(run_id, windows, *, dsn, graphdb_url, functions=None, limit=1000,
              warmups=1, repetitions=5, mapping_discovery="reports/tep_nexus_mapping_discovery.json",
              temporal_coverage="reports/tep_nexus_temporal_coverage.json",
              evaluator=evaluate):
    if (type(warmups) is not int or warmups < 0 or
            type(repetitions) is not int or not 1 <= repetitions <= 100):
        raise ValueError("Warmups must be nonnegative and repetitions between 1 and 100")
    if not windows or any(len(w) != 2 or any(not isinstance(x, (int, float)) or
            isinstance(x, bool) or not math.isfinite(x) for x in w) or
            w[0] < 0 or w[1] < w[0] for w in windows):
        raise ValueError("Invalid simulation-time windows")
    rows = []
    runs = []
    for index in range(warmups + repetitions):
        measured = index >= warmups
        report = evaluator(
            run_id, windows, dsn=dsn, graphdb_url=graphdb_url,
            functions=functions, limit=limit,
            mapping_discovery=mapping_discovery, temporal_coverage=temporal_coverage)
        if report["summary"]["status"] != "PASS":
            raise RuntimeError(f"Evaluation failed during {'measurement' if measured else 'warmup'} {index + 1}: "
                               + json.dumps(report["summary"]))
        if not measured:
            continue
        repetition = index - warmups + 1
        runs.append({"repetition": repetition, "summary": report["summary"]})
        for case in report["cases"]:
            rows.append({
                "repetition": repetition,
                "function": case["function"],
                "startSeconds": case["windowSeconds"][0],
                "endSeconds": case["windowSeconds"][1],
                "latencyMs": case["latencyMs"],
                "observationCount": case["observationCount"],
                "truncated": case["truncated"],
                "status": case["status"],
            })
    latencies = [r["latencyMs"] for r in rows]
    summary = {
        "measuredCases": len(rows),
        "repetitions": repetitions,
        "warmupRounds": warmups,
        "meanLatencyMs": round(statistics.mean(latencies), 3),
        "medianLatencyMs": round(statistics.median(latencies), 3),
        "p50LatencyMs": percentile(latencies, 50),
        "p95LatencyMs": percentile(latencies, 95),
        "p99LatencyMs": percentile(latencies, 99),
        "minLatencyMs": min(latencies),
        "maxLatencyMs": max(latencies),
        "truncatedCases": sum(r["truncated"] for r in rows),
        "status": "PASS",
    }
    return {
        "interface": "TEP NEXUS repeated VTKG performance benchmark v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version.split()[0],
                        "platform": platform.platform(),
                        "processor": platform.processor()},
        "configuration": {"runId": run_id, "windowsSeconds": windows,
                          "functions": functions if functions is not None else "ALL_ELIGIBLE",
                          "limit": limit, "warmups": warmups, "repetitions": repetitions,
                          "mappingDiscovery": mapping_discovery,
                          "temporalCoverage": temporal_coverage},
        "summary": summary, "runs": runs, "measurements": rows,
        "methodology": {
            "percentile": "nearest_rank",
            "timing": "per-case GraphDB mapping resolution + TimescaleDB retrieval + virtual projection; "
                      "excludes evaluator post-query correctness checks and Ollama planning",
            "warmup": "complete evaluation rounds discarded",
            "ordering": "fixed function/window order; not randomized",
            "cache": "not controlled; warmup is not proof of cold/warm cache state",
            "parallelism": "sequential single client",
        },
        "limitations": [
            "No direct TimescaleDB baseline or RDF-materialization baseline.",
            "No independent semantic correctness oracle or physical sensor binding verification.",
            "Per-stage timing and throughput are not measured.",
            "Percentiles across mixed functions/windows are descriptive, not per-workload guarantees.",
            "Truncated retrievals are reported, not treated as full-window coverage.",
        ],
    }


def write_outputs(report, json_path, csv_path):
    json_path, csv_path = Path(json_path), Path(csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    fields = ["repetition", "function", "startSeconds", "endSeconds",
              "latencyMs", "observationCount", "truncated", "status"]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["measurements"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--window", nargs=2, type=float, action="append", required=True,
                   metavar=("START_SECONDS", "END_SECONDS"))
    p.add_argument("--function", action="append", dest="functions")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", default="reports/tep_nexus_performance_benchmark.json")
    p.add_argument("--csv", default="reports/tep_nexus_performance_benchmark.csv")
    a = p.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    report = benchmark(a.run_id, a.window, dsn=dsn, graphdb_url=a.graphdb_url,
                       functions=a.functions, limit=a.limit, warmups=a.warmups,
                       repetitions=a.repetitions, mapping_discovery=a.mapping_discovery,
                       temporal_coverage=a.temporal_coverage)
    write_outputs(report, a.output, a.csv)
    print(json.dumps({"json": a.output, "csv": a.csv, **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
