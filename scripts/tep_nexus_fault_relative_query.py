"""Fault-relative virtual Temporal KG query for TEP NEXUS.

Reuses the existing Ollama engineering-function planner and live GraphDB mapping
resolver. TimescaleDB is queried read-only; no model-authored SQL is executed.
Recorded fault commands are not evidence of a physical process fault.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from process_sim.api.temporal_intervals import (
    classify_observation,
    derive_fault_command_intervals,
)
from tep_nexus_function_registry import (
    load_supported_functions,
    resolve_supported_mapping,
)
from tep_nexus_ollama_query_planner import plan_question, validate_plan


def retrieve_fault_relative_evidence(
    dsn, run_id, signal, *, window_minutes=10, sample_limit=1000,
    event_limit=5000, connection_factory=None,
):
    """Return event-centered measurements and command-derived intervals.

    Window is in simulation minutes. Each event is independently centered.
    A complete event history is required before interval closure is asserted.
    """
    run = str(UUID(str(run_id)))
    if not isinstance(signal, str) or not signal:
        raise ValueError("Signal is required")
    if not 0 < window_minutes <= 120:
        raise ValueError("Window must be within (0, 120] simulation minutes")
    if not 1 <= sample_limit <= 5000 or not 1 <= event_limit <= 5000:
        raise ValueError("Invalid query limits")

    connect = connection_factory or psycopg.connect
    with connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                # Count all commands to avoid incorrectly treating a truncated
                # event history as complete.
                cur.execute(
                    "SELECT count(*) FROM public.fault_events WHERE run_id=%s::uuid",
                    (run,),
                )
                event_count = cur.fetchone()[0]
                if event_count > event_limit:
                    raise ValueError("Fault event history exceeds event_limit")
                cur.execute(
                    """SELECT event_id, run_id, observed_at, simulation_time_hours,
                              action, fault_id, target
                       FROM public.fault_events
                       WHERE run_id=%s::uuid
                       ORDER BY simulation_time_hours, observed_at, event_id""",
                    (run,),
                )
                rows = cur.fetchall()
                events = [
                    {
                        "event_id": str(eid), "run_id": str(rid),
                        "observed_at": stamp, "simulation_time_hours": float(t),
                        "action": action, "fault_id": fault, "target": target,
                    }
                    for eid, rid, stamp, t, action, fault, target in rows
                ]
                relevant = [
                    event for event in events
                    if str(event["target"] or "").upper() == signal.upper()
                ]
                # Derive intervals from all commands for this run, then retain
                # only intervals whose injection targeted the selected signal.
                intervals_result = derive_fault_command_intervals(
                    run, events, complete=True,
                )
                relevant_start_ids = {
                    event["event_id"] for event in relevant
                    if event["action"] == "inject"
                }
                intervals = [
                    interval for interval in intervals_result["intervals"]
                    if interval["startEventId"] in relevant_start_ids
                ]
                # Include a fault command even if its interval is anomalous.
                centers = sorted({e["simulation_time_hours"] for e in relevant})
                windows = []
                for center in centers:
                    low = max(0.0, center - window_minutes / 60.0)
                    high = center + window_minutes / 60.0
                    cur.execute(
                        """SELECT simulation_time_hours, value, observed_at
                           FROM public.signal_samples
                           WHERE run_id=%s::uuid AND signal_id=%s
                             AND simulation_time_hours >= %s
                             AND simulation_time_hours <= %s
                           ORDER BY simulation_time_hours, observed_at
                           LIMIT %s""",
                        (run, signal, low, high, sample_limit + 1),
                    )
                    sample_rows = cur.fetchall()
                    truncated = len(sample_rows) > sample_limit
                    samples = []
                    for t, value, observed in sample_rows[:sample_limit]:
                        labels = [
                            {
                                "faultId": interval["faultId"],
                                "relation": classify_observation(interval, float(t)),
                            }
                            for interval in intervals
                        ]
                        samples.append({
                            "simulationTimeHours": float(t),
                            "value": float(value),
                            "observedAt": observed.isoformat(),
                            "temporalRelations": labels,
                        })
                    windows.append({
                        "centerSimulationHours": center,
                        "lowerSimulationHours": low,
                        "upperSimulationHours": high,
                        "truncated": truncated,
                        "samples": samples,
                    })
                cur.execute(
                    """SELECT simulation_time_hours, value, observed_at
                       FROM public.signal_samples
                       WHERE run_id=%s::uuid AND signal_id=%s
                       ORDER BY observed_at DESC LIMIT 1""",
                    (run, signal),
                )
                latest = cur.fetchone()

    latest_record = None
    if latest:
        observed = latest[2].astimezone(timezone.utc)
        latest_record = {
            "simulationTimeHours": float(latest[0]),
            "value": float(latest[1]),
            "observedAt": observed.isoformat(),
            "recordAgeSeconds": round(
                (datetime.now(timezone.utc) - observed).total_seconds(), 3
            ),
        }
    return {
        "runId": run,
        "signal": signal,
        "sources": ["TimescaleDB signal_samples", "TimescaleDB fault_events"],
        "latestPersisted": latest_record,
        "faultCommands": [
            {**e, "observed_at": e["observed_at"].isoformat()}
            for e in relevant
        ],
        "faultCommandIntervals": intervals,
        "intervalAnomalies": intervals_result["anomalies"],
        "windows": windows,
        "limitations": [
            "Fault intervals represent recorded operator commands, not verified physical states.",
            "OPEN_UNCONFIRMED does not establish a cleared fault or a physical fault effect.",
            "Measurement freshness is measured from observed_at; persisted data is not necessarily live OPC UA data.",
            "Signal mapping must be independently checked against GraphDB.",
        ],
    }


def execute_question(
    question, run_id, *, dsn, graphdb_url, ollama_url,
    model="llama3.1:8b",
    mapping_discovery="reports/tep_nexus_mapping_discovery.json",
    temporal_coverage="reports/tep_nexus_temporal_coverage.json",
    sample_limit=1000,
):
    """LLM plan -> validated function -> live GraphDB mapping -> historian."""
    registry = load_supported_functions(mapping_discovery, temporal_coverage, run_id)
    raw = plan_question(ollama_url, model, question, registry)
    plan = validate_plan(raw, question, registry)
    mapping = resolve_supported_mapping(
        graphdb_url, plan["engineering_function"], registry
    )
    evidence = retrieve_fault_relative_evidence(
        dsn, run_id, mapping["operational_signal"],
        window_minutes=plan["history_window_minutes"],
        sample_limit=sample_limit,
    )
    return {
        "question": question,
        "validatedPlan": plan,
        "engineeringMapping": mapping,
        "temporalEvidence": evidence,
        "provenance": {
            "engineering": "GraphDB, revalidated against run-scoped mapping snapshot",
            "measurements": "TimescaleDB",
            "faultEvents": "TimescaleDB",
            "physicalSensorBinding": "NOT_VERIFIED",
            "mappingConfidence": "PROVISIONAL",
        },
    }



def write_snapshot_artifacts(target, report, analysis, timeline, explanation):
    """Write related artifacts from a single evidence snapshot.

    Each file is atomically replaced to avoid partially written JSON/Markdown;
    the collection is not a multi-file atomic transaction.
    """
    from pathlib import Path
    from tempfile import NamedTemporaryFile
    import os

    from tep_nexus_grounded_explanation import render_markdown

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        target: json.dumps(report, indent=2, allow_nan=False),
        target.with_name("tep_nexus_fault_relative_analysis.json"):
            json.dumps(analysis, indent=2, allow_nan=False),
        target.with_name("tep_nexus_fault_relative_timeline.html"): timeline,
    }
    if explanation is not None:
        artifacts[target.with_name("tep_nexus_grounded_explanation.json")] = (
            json.dumps(explanation, indent=2, allow_nan=False)
        )
        artifacts[target.with_name("tep_nexus_grounded_explanation.md")] = (
            render_markdown(explanation)
        )
    # Stage every file before publishing any of them.
    staged = {}
    try:
        for path, contents in artifacts.items():
            with NamedTemporaryFile(mode="w", encoding="utf-8",
                                    dir=path.parent, prefix=".tep_nexus_",
                                    suffix=".tmp", delete=False) as handle:
                handle.write(contents)
                staged[path] = Path(handle.name)
        for path, temp in staged.items():
            os.replace(temp, path)
    finally:
        for temp in staged.values():
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--sample-limit", type=int, default=1000)
    parser.add_argument("--watch", action="store_true", help="Refresh historian evidence without replanning")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between refreshes")
    parser.add_argument("--iterations", type=int, default=5, help="Number of refreshes in watch mode")
    parser.add_argument("--output", default="reports/tep_nexus_fault_relative_query.json")
    parser.add_argument("--no-explanation", action="store_true", help="Skip grounded explanation files")
    parser.add_argument("--explanation-ollama", choices=("final", "each", "none"), default="final",
                        help="Ollama on final iteration (default), every iteration, or never")
    args = parser.parse_args()
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN must be configured")
    if args.interval <= 0 or args.iterations < 1:
        parser.error("--interval and --iterations must be positive")
    result = execute_question(
        args.question, args.run_id, dsn=dsn, graphdb_url=args.graphdb_url,
        ollama_url=args.ollama_url, model=args.model,
        mapping_discovery=args.mapping_discovery,
        temporal_coverage=args.temporal_coverage,
        sample_limit=args.sample_limit,
    )
    from pathlib import Path
    from tep_nexus_fault_relative_analysis import analyze, render_html
    from tep_nexus_grounded_explanation import generate
    import time
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    analysis_path = target.with_name("tep_nexus_fault_relative_analysis.json")
    timeline_path = target.with_name("tep_nexus_fault_relative_timeline.html")
    explanation_path = target.with_name("tep_nexus_grounded_explanation.json")
    markdown_path = target.with_name("tep_nexus_grounded_explanation.md")
    repetitions = args.iterations if args.watch else 1
    for index in range(repetitions):
        if index:
            # Preserve the validated plan and GraphDB mapping; re-query only
            # the changing historian data. This does not contact OPC UA.
            result["temporalEvidence"] = retrieve_fault_relative_evidence(
                dsn, args.run_id, result["engineeringMapping"]["operational_signal"],
                window_minutes=result["validatedPlan"]["history_window_minutes"],
                sample_limit=args.sample_limit,
            )
        # Generate all artifacts from this same in-memory historian snapshot.
        # In watch mode, deterministic explanations update each iteration;
        # Ollama runs only at the final iteration unless explicitly requested.
        analysis = analyze(result["temporalEvidence"])
        timeline = render_html(result)
        explanation = None
        if not args.no_explanation:
            use_ollama = (args.explanation_ollama == "each" or
                          (args.explanation_ollama == "final" and index == repetitions - 1))
            explanation = generate(result, analysis,
                                   ollama_url=args.ollama_url if use_ollama else None,
                                   model=args.model)
        write_snapshot_artifacts(
            target, result, analysis, timeline, explanation,
        )
        latest = result["temporalEvidence"]["latestPersisted"]
        print(json.dumps({
            "iteration": index + 1,
            "output": str(target),
            "analysis": str(analysis_path),
            "timeline": str(timeline_path),
            "function": result["validatedPlan"]["engineering_function"],
            "signal": result["temporalEvidence"]["signal"],
            "faultCommands": len(result["temporalEvidence"]["faultCommands"]),
            "intervals": len(result["temporalEvidence"]["faultCommandIntervals"]),
            "windows": len(result["temporalEvidence"]["windows"]),
            "latestObservedAt": latest["observedAt"] if latest else None,
            "recordAgeSeconds": latest["recordAgeSeconds"] if latest else None,
            "explanation": str(explanation_path) if explanation is not None else None,
            "explanationStatus": explanation["status"] if explanation is not None else None,
            "ollamaStatus": explanation["ollama"]["status"] if explanation is not None else None,
        }, indent=2))
        if index < repetitions - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
