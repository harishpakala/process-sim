"""Read-only, fault-independent live virtual temporal graph query interface.

GraphDB resolves the engineering mapping; TimescaleDB supplies bounded
observations on demand. No RDF materialization or LLM-generated SQL.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg

from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_virtual_graph import project


def validate_request(function, run_id, start_seconds, end_seconds, limit):
    if not isinstance(function, str) or not function.strip():
        raise ValueError("Engineering function required")
    run = str(UUID(str(run_id)))
    for value in (start_seconds, end_seconds):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Simulation-time bounds must be finite numbers")
    if start_seconds < 0 or end_seconds < start_seconds:
        raise ValueError("Invalid simulation-time interval")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("Limit must be an integer between 1 and 5000")
    return {"engineering_function": function.strip(), "run_id": run,
            "start_simulation_seconds": float(start_seconds),
            "end_simulation_seconds": float(end_seconds), "limit": limit}


def retrieve_observations(dsn, request, signal, *, connection_factory=None):
    """Parameter-bound read-only SQL; ordered and capped with a truncation probe."""
    connect = connection_factory or psycopg.connect
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
                     request["limit"] + 1),
                )
                rows = cur.fetchall()
    truncated = len(rows) > request["limit"]
    samples = []
    for hours, value, observed in rows[:request["limit"]]:
        if not math.isfinite(float(hours)) or not math.isfinite(float(value)):
            raise ValueError("Non-finite historian measurement")
        samples.append({
            "simulationTimeHours": float(hours),
            "value": float(value),
            "observedAt": observed.isoformat(),
            "temporalRelations": [],
        })
    return {"samples": samples, "truncated": truncated}


def execute(request, *, dsn, graphdb_url,
            mapping_discovery="reports/tep_nexus_mapping_discovery.json",
            temporal_coverage="reports/tep_nexus_temporal_coverage.json",
            mapping_resolver=resolve_supported_mapping,
            registry_loader=load_supported_functions,
            observation_retriever=retrieve_observations):
    """Resolve semantic mapping, fetch historian, project graph from one snapshot."""
    req = validate_request(request["engineering_function"], request["run_id"],
                           request["start_simulation_seconds"],
                           request["end_simulation_seconds"], request["limit"])
    registry = registry_loader(mapping_discovery, temporal_coverage, req["run_id"])
    mapping = mapping_resolver(graphdb_url, req["engineering_function"], registry)
    if (mapping["engineering_function"] != req["engineering_function"] or
            mapping["operational_signal"] != registry[req["engineering_function"]]["operational_signal"]):
        raise ValueError("Live mapping differs from requested/registered function")
    temporal = observation_retriever(dsn, req, mapping["operational_signal"])
    query = {
        "validatedPlan": {"engineering_function": req["engineering_function"]},
        "engineeringMapping": mapping,
        "temporalEvidence": {
            "runId": req["run_id"], "signal": mapping["operational_signal"],
            "faultCommands": [],
            "windows": [{
                "samples": temporal["samples"], "truncated": temporal["truncated"],
                "lowerSimulationHours": req["start_simulation_seconds"] / 3600.0,
                "upperSimulationHours": req["end_simulation_seconds"] / 3600.0,
            }],
        },
    }
    graph = project(query)
    graph["interface"] = "TEP NEXUS live read-only virtual temporal graph query v1"
    graph["snapshotScope"] = "single bounded historian retrieval with live GraphDB mapping recheck"
    graph["request"] = req
    graph["result"] = {
        "observationCount": len(temporal["samples"]),
        "truncated": temporal["truncated"],
        "timeBasis": "simulation_time",
        "retrievedAtUtc": datetime.now(timezone.utc).isoformat(),
    }
    graph["provenance"] = {
        "semanticSource": "GraphDB AAS repository",
        "temporalSource": "TimescaleDB public.signal_samples",
        "runIdentitySource": "operator_supplied",
        "mappingConfidence": "PROVISIONAL",
        "physicalSensorBinding": "NOT_VERIFIED",
        "sharedRunProvenance": "NOT_VERIFIED",
    }
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--function", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-seconds", type=float, required=True)
    parser.add_argument("--end-seconds", type=float, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--output", default="reports/tep_nexus_live_virtual_graph.json")
    args = parser.parse_args()
    if not os.environ.get("TEP_TIMESCALE_DSN"):
        parser.error("TEP_TIMESCALE_DSN must be configured")
    graph = execute({
        "engineering_function": args.function, "run_id": args.run_id,
        "start_simulation_seconds": args.start_seconds,
        "end_simulation_seconds": args.end_seconds, "limit": args.limit,
    }, dsn=os.environ["TEP_TIMESCALE_DSN"], graphdb_url=args.graphdb_url,
        mapping_discovery=args.mapping_discovery,
        temporal_coverage=args.temporal_coverage)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(path), "nodes": len(graph["nodes"]),
                      "edges": len(graph["edges"]), **graph["result"],
                      "materializedInGraphDB": False}, indent=2))


if __name__ == "__main__":
    main()
