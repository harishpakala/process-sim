"""Read-only independent source-to-VTKG correctness and provenance audit.

Uses raw GraphDB SPARQL bindings and a separate parameterized TimescaleDB SQL
query as reference oracles. No fault causation or physical binding claims.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests

from tep_nexus_function_registry import load_supported_functions
from tep_nexus_live_virtual_graph import execute, validate_request
from tep_nexus_mapping_discovery import SPARQL


def reference_mapping(graphdb_url, function, *, post=requests.post):
    response = post(graphdb_url, data={"query": SPARQL},
                    headers={"Accept": "application/sparql-results+json"}, timeout=30)
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    candidates = set()
    for row in bindings:
        if row["functionId"]["value"].strip() == function:
            candidates.add((row["functionRef"]["value"].strip(),
                            row["signal"]["value"].strip(),
                            row["asset"]["value"].strip()))
    if len(candidates) != 1 or not all(next(iter(candidates))):
        raise ValueError("Reference GraphDB mapping missing or ambiguous")
    ref, signal, asset = next(iter(candidates))
    return {"function_reference": ref, "operational_signal": signal, "asset_uri": asset}


def reference_samples(dsn, request, signal, *, connect=psycopg.connect):
    with connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT simulation_time_hours, value, observed_at
                       FROM public.signal_samples
                       WHERE run_id = %s::uuid AND signal_id = %s
                         AND simulation_time_hours >= %s
                         AND simulation_time_hours <= %s
                       ORDER BY simulation_time_hours, observed_at, value
                       LIMIT %s""",
                    (request["run_id"], signal,
                     request["start_simulation_seconds"] / 3600.0,
                     request["end_simulation_seconds"] / 3600.0,
                     request["limit"] + 1))
                rows = cur.fetchall()
    return {
        "rows": [(float(h), float(v), t.astimezone(timezone.utc).isoformat(timespec="microseconds"))
                 for h, v, t in rows[:request["limit"]]],
        "truncated": len(rows) > request["limit"],
    }


def audit(run_id, windows, *, dsn, graphdb_url, functions=None, limit=1000,
          mapping_discovery="reports/tep_nexus_mapping_discovery.json",
          temporal_coverage="reports/tep_nexus_temporal_coverage.json",
          registry_loader=load_supported_functions, virtual_executor=execute,
          mapping_reader=reference_mapping, sample_reader=reference_samples):
    if not windows:
        raise ValueError("At least one window is required")
    registry = registry_loader(mapping_discovery, temporal_coverage, run_id)
    selected = sorted(registry) if functions is None else list(functions)
    if not selected or len(selected) != len(set(selected)) or any(f not in registry for f in selected):
        raise ValueError("Unsupported or duplicated engineering function")
    cases = []
    for function in selected:
        for start, end in windows:
            req = validate_request(function, run_id, start, end, limit)
            try:
                source_mapping = mapping_reader(graphdb_url, function)
                expected = registry[function]
                graph = virtual_executor(req, dsn=dsn, graphdb_url=graphdb_url,
                                         mapping_discovery=mapping_discovery,
                                         temporal_coverage=temporal_coverage)
                nodes = graph["nodes"]
                functions_found = [n for n in nodes if n["type"] == "EngineeringFunction"]
                signals = [n for n in nodes if n["type"] == "OperationalSignal"]
                assets = [n for n in nodes if n["type"] == "EngineeringAsset"]
                observations = [n for n in nodes if n["type"] == "VirtualObservation"]
                reference = sample_reader(dsn, req, source_mapping["operational_signal"])
                actual_rows = sorted(
                    (float(n["simulationTimeHours"]), float(n["value"]),
                     datetime.fromisoformat(n["observedAt"]).astimezone(timezone.utc)
                     .isoformat(timespec="microseconds"))
                    for n in observations)
                checks = {
                    "graphdb_mapping_matches_registry": source_mapping == expected,
                    "function_matches_source": len(functions_found) == 1 and
                        functions_found[0]["localId"] == function,
                    "signal_matches_source": len(signals) == 1 and
                        signals[0]["signalId"] == source_mapping["operational_signal"],
                    "asset_matches_source": len(assets) == 1 and
                        assets[0]["id"] == source_mapping["asset_uri"],
                    "historian_rows_match_reference": actual_rows == sorted(reference["rows"]),
                    "count_matches_reference": graph["result"]["observationCount"] == len(reference["rows"]),
                    "truncation_matches_reference": graph["result"]["truncated"] == reference["truncated"],
                    "provenance_caveats": graph["provenance"]["mappingConfidence"] == "PROVISIONAL"
                        and graph["provenance"]["physicalSensorBinding"] == "NOT_VERIFIED"
                        and graph["provenance"]["sharedRunProvenance"] == "NOT_VERIFIED",
                    "no_graphdb_materialization": graph["materializedInGraphDB"] is False,
                    "run_identity_matches": len([n for n in nodes if n["type"] == "SimulationRun"
                                                 and n["runId"] == req["run_id"]]) == 1,
                }
                cases.append({"function": function, "windowSeconds": [start, end],
                              "status": "PASS" if all(checks.values()) else "FAIL",
                              "checks": checks, "observationCount": len(observations),
                              "truncated": reference["truncated"]})
            except Exception as exc:
                cases.append({"function": function, "windowSeconds": [start, end],
                              "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
    passed = sum(c["status"] == "PASS" for c in cases)
    return {
        "interface": "TEP NEXUS independent semantic-temporal correctness audit v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "runId": run_id, "windowsSeconds": windows, "functions": selected,
        "cases": cases,
        "summary": {"status": "PASS" if passed == len(cases) else "FAIL",
                    "caseCount": len(cases), "passedCases": passed,
                    "failedOrErroredCases": len(cases) - passed,
                    "truncatedCases": sum(c.get("truncated", False) for c in cases)},
        "limitations": [
            "Reference SQL is independently executed but uses the same source schema and selection semantics.",
            "Reference SPARQL uses the existing discovery query, not an independently authored ontology oracle.",
            "GraphDB and TimescaleDB reads are not an atomic distributed snapshot.",
            "Observation equality uses content tuples, not independently verified database row IDs.",
            "No physical sensor identity, measurement units, or shared-run provenance are verified.",
            "No storage-level audit proving absence of RDF materialization is performed.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--window", nargs=2, type=float, action="append", required=True)
    p.add_argument("--function", action="append", dest="functions")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", default="reports/tep_nexus_correctness_audit.json")
    a = p.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("TEP_TIMESCALE_DSN is not set")
    result = audit(a.run_id, a.window, dsn=dsn, graphdb_url=a.graphdb_url,
                   functions=a.functions, limit=a.limit,
                   mapping_discovery=a.mapping_discovery,
                   temporal_coverage=a.temporal_coverage)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(out), **result["summary"]}, indent=2))
    if result["summary"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
