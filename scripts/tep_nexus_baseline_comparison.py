"""Paired VTKG versus direct TimescaleDB read-only benchmark.

Pre-resolves signal mappings from run-scoped registry; the direct baseline
does not independently establish engineering semantics. Alternates execution
order across rounds. Compares exact observation fingerprints and truncation.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_function_registry import load_supported_functions
from tep_nexus_live_virtual_graph import execute, retrieve_observations, validate_request
from tep_nexus_performance_benchmark import percentile


def compare(run_id, windows, *, dsn, graphdb_url, functions=None, limit=1000,
            warmups=1, repetitions=10,
            mapping_discovery="reports/tep_nexus_mapping_discovery.json",
            temporal_coverage="reports/tep_nexus_temporal_coverage.json",
            registry_loader=load_supported_functions, virtual_executor=execute,
            direct_retriever=retrieve_observations, clock=time.perf_counter):
    if type(warmups) is not int or warmups < 0 or type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("Invalid warmups or repetitions")
    if not windows:
        raise ValueError("At least one window required")
    registry = registry_loader(mapping_discovery, temporal_coverage, run_id)
    selected = sorted(registry) if functions is None else list(functions)
    if not selected or len(selected) != len(set(selected)) or any(f not in registry for f in selected):
        raise ValueError("Unsupported or duplicate engineering function")
    workload = []
    for function in selected:
        for start, end in windows:
            req = validate_request(function, run_id, start, end, limit)
            workload.append((req, registry[function]["operational_signal"]))
    rows = []
    for round_index in range(warmups + repetitions):
        measured = round_index >= warmups
        for req, signal in workload:
            results = {}
            order = ("virtual", "direct") if round_index % 2 == 0 else ("direct", "virtual")
            for method in order:
                t0 = clock()
                if method == "virtual":
                    graph = virtual_executor(
                        req, dsn=dsn, graphdb_url=graphdb_url,
                        mapping_discovery=mapping_discovery, temporal_coverage=temporal_coverage)
                    observations = [n for n in graph["nodes"] if n["type"] == "VirtualObservation"]
                    results[method] = {
                        "latencyMs": (clock() - t0) * 1000,
                        "fingerprints": sorted(n["id"].rsplit("/", 1)[-1] for n in observations),
                        "count": graph["result"]["observationCount"],
                        "truncated": graph["result"]["truncated"],
                        "signal": next((n["signalId"] for n in graph["nodes"]
                                        if n["type"] == "OperationalSignal"), None),
                    }
                else:
                    temporal = direct_retriever(dsn, req, signal)
                    results[method] = {
                        "latencyMs": (clock() - t0) * 1000,
                        "fingerprints": sorted(s["observationFingerprint"] for s in temporal["samples"]),
                        "count": len(temporal["samples"]),
                        "truncated": temporal["truncated"],
                        "signal": signal,
                    }
            v, d = results["virtual"], results["direct"]
            # VTKG observation IDs must contain the original content fingerprint.
            equal = (v["fingerprints"] == d["fingerprints"] and v["count"] == d["count"]
                     and v["truncated"] == d["truncated"] and v["signal"] == d["signal"])
            if not equal:
                raise RuntimeError(f"VTKG/direct retrieval mismatch for {req['engineering_function']} "
                                   f"window {req['start_simulation_seconds']}..{req['end_simulation_seconds']}")
            if measured:
                rows.append({
                    "repetition": round_index - warmups + 1,
                    "function": req["engineering_function"],
                    "signal": signal,
                    "startSeconds": req["start_simulation_seconds"],
                    "endSeconds": req["end_simulation_seconds"],
                    "virtualMs": round(v["latencyMs"], 3),
                    "directMs": round(d["latencyMs"], 3),
                    "overheadMs": round(v["latencyMs"] - d["latencyMs"], 3),
                    "observationCount": d["count"],
                    "truncated": d["truncated"],
                    "fingerprintsEqual": True,
                })
    def stats(key):
        vals = [r[key] for r in rows]
        return {"mean": round(statistics.mean(vals), 3),
                "median": round(statistics.median(vals), 3),
                "p95": percentile(vals, 95), "p99": percentile(vals, 99)}
    return {
        "interface": "TEP NEXUS paired virtual-versus-direct benchmark v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "configuration": {"runId": run_id, "functions": selected,
                          "windowsSeconds": windows, "limit": limit,
                          "warmups": warmups, "repetitions": repetitions},
        "summary": {"status": "PASS", "pairedCases": len(rows),
                    "matchingPairs": len(rows),
                    "truncatedPairs": sum(r["truncated"] for r in rows),
                    "virtualLatencyMs": stats("virtualMs"),
                    "directLatencyMs": stats("directMs"),
                    "overheadMs": stats("overheadMs")},
        "measurements": rows,
        "methodology": {
            "comparison": "same run, signal, simulation-time bounds, limit, and content fingerprints",
            "direct": "pre-resolved signal from provisional run-scoped registry; read-only TimescaleDB",
            "virtual": "live GraphDB mapping recheck, TimescaleDB retrieval, graph projection",
            "ordering": "alternating virtual/direct order each round; sequential single client",
            "percentiles": "nearest rank; descriptive for observed mixed workloads",
        },
        "limitations": [
            "The direct baseline uses pre-resolved provisional mappings, not independent engineering semantics.",
            "Separate sequential queries are not a common database snapshot; concurrent writes can cause mismatches.",
            "Fingerprints are content identities, not verified historian primary keys.",
            "No Ollama planning, RDF-materialization baseline, or per-stage instrumentation.",
            "Cache state is uncontrolled; timings include client connection overhead.",
        ],
    }


def write_outputs(report, json_path, csv_path):
    j, c = Path(json_path), Path(csv_path)
    j.parent.mkdir(parents=True, exist_ok=True)
    c.parent.mkdir(parents=True, exist_ok=True)
    j.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    with c.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report["measurements"][0]))
        writer.writeheader()
        writer.writerows(report["measurements"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--window", action="append", nargs=2, type=float, required=True)
    p.add_argument("--function", action="append", dest="functions")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument("--repetitions", type=int, default=10)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", default="reports/tep_nexus_baseline_comparison.json")
    p.add_argument("--csv", default="reports/tep_nexus_baseline_comparison.csv")
    a = p.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    report = compare(a.run_id, a.window, dsn=dsn, graphdb_url=a.graphdb_url,
                     functions=a.functions, limit=a.limit, warmups=a.warmups,
                     repetitions=a.repetitions, mapping_discovery=a.mapping_discovery,
                     temporal_coverage=a.temporal_coverage)
    write_outputs(report, a.output, a.csv)
    print(json.dumps({"json": a.output, "csv": a.csv, **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
