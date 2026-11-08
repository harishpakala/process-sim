"""Reproducible read-only TEP NEXUS semantic-temporal evaluation.

Runs bounded live graph queries across eligible engineering functions and
simulation-time windows. No fault-effect or physical-provenance claims.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from tep_nexus_function_registry import load_supported_functions
from tep_nexus_live_virtual_graph import execute as execute_live
from tep_nexus_graph_operators import get_observations, resolve_function, traverse_relationships


def evaluate(run_id, windows, *, dsn, graphdb_url,
             mapping_discovery="reports/tep_nexus_mapping_discovery.json",
             temporal_coverage="reports/tep_nexus_temporal_coverage.json",
             limit=1000, functions=None, registry_loader=load_supported_functions,
             executor=execute_live, clock=time.perf_counter):
    if not windows or any(len(w) != 2 or w[0] < 0 or w[1] < w[0] for w in windows):
        raise ValueError("Provide nonnegative ordered simulation-second windows")
    registry = registry_loader(mapping_discovery, temporal_coverage, run_id)
    selected = sorted(registry) if functions is None else list(functions)
    if not selected or len(selected) != len(set(selected)) or any(f not in registry for f in selected):
        raise ValueError("Requested function is unsupported or duplicated")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5000:
        raise ValueError("Limit must be between 1 and 5000")
    results = []
    for function in selected:
        for start, end in windows:
            request = {"engineering_function": function, "run_id": run_id,
                       "start_simulation_seconds": start,
                       "end_simulation_seconds": end, "limit": limit}
            t0 = clock()
            try:
                graph = executor(request, dsn=dsn, graphdb_url=graphdb_url,
                                 mapping_discovery=mapping_discovery,
                                 temporal_coverage=temporal_coverage)
                elapsed = (clock() - t0) * 1000
                node = resolve_function(graph, function)["function"]
                edges = traverse_relationships(graph, node["id"])
                observations = get_observations(graph, start_seconds=start, end_seconds=end)
                observed_ids = [n["id"] for n in observations]
                checks = {
                    "function_resolved": node["localId"] == function,
                    "signal_edge_present": any(e["predicate"] == "mapsToSignal" for e in edges),
                    "asset_edge_present": any(e["predicate"] == "associatedWithAsset" for e in edges),
                    "observation_count_consistent": len(observations) == graph["result"]["observationCount"],
                    "observation_ids_unique": len(set(observed_ids)) == len(observed_ids),
                    "identity_is_source_primary_key": all(
                        n["identityScope"] == "SOURCE_COMPOSITE_PRIMARY_KEY_SHA256"
                        for n in observations),
                    "no_rdf_materialization": graph["materializedInGraphDB"] is False,
                    "provenance_caveats_preserved": (
                        graph["provenance"]["physicalSensorBinding"] == "NOT_VERIFIED"
                        and graph["provenance"]["sharedRunProvenance"] == "NOT_VERIFIED"),
                }
                results.append({"function": function, "windowSeconds": [start, end],
                                "status": "PASS" if all(checks.values()) else "FAIL",
                                "checks": checks, "latencyMs": round(elapsed, 3),
                                "observationCount": len(observations),
                                "truncated": graph["result"]["truncated"],
                                "_observations": observations})
            except Exception as exc:
                results.append({"function": function, "windowSeconds": [start, end],
                                "status": "ERROR", "error": f"{type(exc).__name__}: {exc}",
                                "latencyMs": round((clock() - t0) * 1000, 3)})
    overlaps = []
    for function in selected:
        entries = [r for r in results if r["function"] == function and r["status"] != "ERROR"]
        for i, left in enumerate(entries):
            for right in entries[i + 1:]:
                a, b = left["windowSeconds"], right["windowSeconds"]
                lower, upper = max(a[0], b[0]), min(a[1], b[1])
                if lower > upper:
                    continue
                if left["truncated"] or right["truncated"]:
                    overlaps.append({"function": function, "windows": [a, b],
                                     "status": "NOT_ASSESSED_TRUNCATED"})
                    continue
                def common(entry):
                    return {n["id"] for n in entry["_observations"]
                            if lower <= n["simulationTimeHours"] * 3600 <= upper}
                equal = common(left) == common(right)
                overlaps.append({"function": function, "windows": [a, b],
                                 "status": "PASS" if equal else "FAIL",
                                 "sharedObservationCount": len(common(left) & common(right))})
    for r in results:
        r.pop("_observations", None)
    latencies = [r["latencyMs"] for r in results if r["status"] != "ERROR"]
    failures = sum(r["status"] != "PASS" for r in results)
    failures += sum(r["status"] == "FAIL" for r in overlaps)
    return {
        "interface": "TEP NEXUS semantic-temporal evaluation v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "runId": run_id, "timeBasis": "simulation_time",
        "functions": selected, "windowsSeconds": windows,
        "cases": results, "overlapChecks": overlaps,
        "summary": {"caseCount": len(results), "passedCases": sum(r["status"] == "PASS" for r in results),
                    "failedOrErroredCases": sum(r["status"] != "PASS" for r in results),
                    "overlapChecksPassed": sum(r["status"] == "PASS" for r in overlaps),
                    "overlapChecksFailed": sum(r["status"] == "FAIL" for r in overlaps),
                    "truncatedCases": sum(r.get("truncated", False) for r in results),
                    "meanLatencyMs": round(statistics.mean(latencies), 3) if latencies else None,
                    "maxLatencyMs": max(latencies, default=None),
                    "status": "PASS" if failures == 0 else "FAIL"},
        "limitations": [
            "Correctness checks are structural; no independent historian ground-truth oracle.",
            "Only run-scoped eligible functions and requested intervals are tested.",
            "Cross-window live identity uses hashes of the verified TimescaleDB composite primary key.",
            "Overlap comparisons are skipped when either window is truncated.",
            "Latencies include GraphDB mapping rechecks and TimescaleDB retrieval; no warmup or statistical benchmark design.",
            "No storage-overhead or near-real-time freshness benchmark is performed.",
            "Physical sensor binding and shared run provenance remain unverified.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--window", nargs=2, type=float, action="append", required=True,
                   metavar=("START_SECONDS", "END_SECONDS"))
    p.add_argument("--function", action="append", dest="functions")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", default="reports/tep_nexus_semantic_temporal_evaluation.json")
    a = p.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    report = evaluate(a.run_id, a.window, dsn=dsn, graphdb_url=a.graphdb_url,
                      mapping_discovery=a.mapping_discovery,
                      temporal_coverage=a.temporal_coverage,
                      limit=a.limit, functions=a.functions)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(out), **report["summary"]}, indent=2))
    if report["summary"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
