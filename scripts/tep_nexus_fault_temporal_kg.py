"""Fault-aware, read-only extension of the virtual Temporal KG.

Command-derived intervals do not establish physical fault activity.
"""
# Created: 2026-11-08
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.api.temporal_intervals import (
    derive_fault_command_intervals, classify_observation,
)

spec = importlib.util.spec_from_file_location(
    "virtual_temporal_kg", Path(__file__).with_name("tep_nexus_virtual_temporal_kg.py")
)
virtual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(virtual)


def fetch_events(dsn, run_id):
    sql = """
SELECT event_id, run_id, observed_at, simulation_time_hours,
       action, fault_id, fault_type, target, magnitude, event_source, metadata
FROM public.fault_events WHERE run_id = %s::uuid
ORDER BY simulation_time_hours, observed_at, event_id
"""
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, (run_id,))
                rows = cur.fetchall()
    return [
        dict(event_id=str(r[0]), run_id=str(r[1]), observed_at=r[2].isoformat(),
             simulation_time_hours=float(r[3]), action=r[4], fault_id=r[5],
             fault_type=r[6], target=r[7], magnitude=r[8],
             event_source=r[9], metadata=r[10])
        for r in rows
    ]


def fetch_boundary(dsn, run_id, signal, seconds, limit=20):
    sql = """
SELECT simulation_time_hours, value, observed_at
FROM public.signal_samples
WHERE run_id = %s::uuid AND signal_id = %s
ORDER BY ABS(simulation_time_hours - %s::double precision), observed_at
LIMIT %s
"""
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, (run_id, signal, seconds / 3600, limit))
                rows = cur.fetchall()
    return [
        dict(simulation_seconds=round(float(r[0]) * 3600, 6),
             value=float(r[1]), observed_at=r[2].isoformat())
        for r in rows
    ]


def augment_graph(graph, run_id, signal, events, intervals, boundary):
    base = "urn:tep-nexus:"
    run_node = base + "run:" + run_id
    signal_node = base + "signal:" + quote(signal, safe="")
    nodes, edges = graph["nodes"], graph["edges"]
    for event in events:
        eid = base + "fault-command:" + quote(event["event_id"], safe="")
        nodes.append(dict(id=eid, type="FaultCommandEvent",
                          **event, evidenceSource="TimescaleDB"))
        edges.append(dict(source=eid, predicate="recordedForRun",
                          target=run_node, evidenceSource="TimescaleDB"))
    for interval in intervals:
        iid = base + "fault-command-interval:" + quote(
            interval["startEventId"], safe=""
        )
        nodes.append(dict(id=iid, type="FaultCommandInterval", **interval))
        for key, predicate in (("startEventId", "derivedFromInjectionCommand"),
                               ("endEventId", "derivedFromClearCommand")):
            if interval[key]:
                edges.append(dict(source=iid, predicate=predicate,
                                  target=base + "fault-command:" + quote(interval[key], safe=""),
                                  evidenceSource="TimescaleDB"))
    for index, sample in enumerate(boundary):
        oid = base + "boundary-observation:" + run_id + ":" + str(index)
        nodes.append(dict(id=oid, type="TemporalObservation", signalId=signal,
                          value=sample["value"], simulationTimeSeconds=sample["simulation_seconds"],
                          recordedAt=sample["observed_at"], queryResultIdentity=True,
                          observationSelection="fault_boundary", evidenceSource="TimescaleDB"))
        edges.extend([
            dict(source=signal_node, predicate="hasTemporalObservation",
                 target=oid, evidenceSource="TimescaleDB"),
            dict(source=oid, predicate="retrievedUsingRunReference",
                 target=run_node, evidenceSource="operator_supplied_run_filter"),
        ])
    observations = [n for n in nodes if n["type"] == "TemporalObservation"]
    for node in observations:
        node["faultCommandRelations"] = {}
        for interval in intervals:
            if interval["target"] != signal:
                continue
            relation = classify_observation(
                interval, node["simulationTimeSeconds"] / 3600
            )
            node["faultCommandRelations"][interval["faultId"]] = relation
            edges.append(dict(
                source=node["id"], predicate="relativeToFaultCommandInterval",
                target=base + "fault-command-interval:" + quote(interval["startEventId"], safe=""),
                temporalRelation=relation, evidenceSource="TimescaleDB",
                interpretation="Command-relative; physical fault state unverified",
            ))
    return graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", default="TI_101")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-minutes", type=float, default=10)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--boundary-limit", type=int, default=20)
    parser.add_argument("--graphdb-url", default=os.getenv(
        "TEP_GRAPHDB_URL", "http://localhost:7200/repositories/AAS"
    ))
    parser.add_argument("--output", default="reports/tep_nexus_fault_temporal_kg.json")
    args = parser.parse_args()
    if args.window_minutes <= 0 or args.limit < 1 or args.boundary_limit < 1:
        parser.error("Window and limits must be positive")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")
    mapping = virtual.resolve_mapping(args.graphdb_url, args.function)
    samples = virtual.fetch_history(
        dsn, args.run_id, mapping["signal"], args.window_minutes, args.limit
    )
    events = fetch_events(dsn, args.run_id)
    derived = derive_fault_command_intervals(args.run_id, events, complete=True)
    by_id = {e["event_id"]: e for e in events}
    intervals = []
    for interval in derived["intervals"]:
        source = by_id[interval["startEventId"]]
        intervals.append(dict(**interval, target=source["target"],
                              faultType=source["fault_type"],
                              magnitude=source["magnitude"],
                              eventSource=source["event_source"]))
    relevant = [i for i in intervals if i["target"] == mapping["signal"]]
    boundary = []
    if relevant:
        seen = {(s["simulation_seconds"], s["observed_at"]) for s in samples}
        for interval in relevant:
            candidates = fetch_boundary(
                dsn, args.run_id, mapping["signal"],
                interval["startSimulationHours"] * 3600, args.boundary_limit
            )
            for sample in candidates:
                key = (sample["simulation_seconds"], sample["observed_at"])
                if key not in seen:
                    boundary.append(sample)
                    seen.add(key)
    graph = virtual.build_graph(args.function, mapping, args.run_id, samples)
    augment_graph(graph, args.run_id, mapping["signal"], events, intervals, boundary)
    report = dict(
        interface="TEP NEXUS Fault-Aware Virtual Temporal KG",
        representation="query-time property graph JSON",
        generatedAtUTC=datetime.now(timezone.utc).isoformat(),
        query=dict(engineeringFunction=args.function, runId=args.run_id,
                   historyWindowSimulationMinutes=args.window_minutes),
        resolvedContext=dict(aasFunctionReference=mapping["functionRef"],
                             operationalSignal=mapping["signal"], assetURI=mapping["asset"],
                             mappingStatus="PROVISIONAL_ENGINEERING_MATCH"),
        latestPersistedObservation=samples[0] if samples else None,
        latestWindowObservationCount=len(samples),
        historyLimitReached=len(samples) >= args.limit,
        faultBoundaryObservationCount=len(boundary),
        observationCount=len(samples) + len(boundary),
        faultEventCount=len(events),
        faultCommandIntervals=intervals,
        faultCommandAnomalies=derived["anomalies"],
        graph=graph,
        limitations=[
            "Command-derived intervals do not verify physical fault states.",
            "OPEN_UNCONFIRMED means no clear command in the retrieved complete run history.",
            "History completeness is relative to persisted fault_events for this run.",
            "Boundary observations supplement, rather than replace, latest-window samples.",
            "Observation identities are local to this query result.",
            "Engineering mapping is provisional and run provenance remains unverified.",
        ],
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Signal:", mapping["signal"])
    print("Fault events:", len(events))
    print("Intervals:", len(intervals))
    print("Boundary observations:", len(boundary))
    print("Total observations:", report["observationCount"])
    print("Graph nodes:", len(graph["nodes"]), "edges:", len(graph["edges"]))
    print("Saved:", path)


if __name__ == "__main__":
    main()
