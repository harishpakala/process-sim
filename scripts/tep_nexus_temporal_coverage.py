"""Read-only TimescaleDB coverage check for discovered GraphDB mappings.

Counts are scoped to the operator-supplied run ID, not evidence of shared
OPC UA/TimescaleDB provenance or physical sensor verification.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg


def build_coverage(discovery, rows):
    """Join discovered candidates to per-signal aggregate rows."""
    counts = {}
    for signal, count, latest_hours in rows:
        counts[str(signal)] = {
            "sample_count": int(count),
            "latest_simulation_seconds": float(latest_hours) * 3600
            if latest_hours is not None else None,
        }
    result = []
    for candidate in discovery["candidates"]:
        mappings = candidate["mappings"]
        entry = {
            "engineering_function": candidate["engineering_function"],
            "mapping_status": candidate["status"],
            "mapping_count": len(mappings),
            "signals": [],
        }
        for mapping in mappings:
            signal = mapping["operational_signal"]
            count = counts.get(signal, {"sample_count": 0, "latest_simulation_seconds": None})
            entry["signals"].append({"signal": signal, **count})
        entry["temporal_coverage_status"] = (
            "HAS_SAMPLES" if len(mappings) == 1 and
            entry["signals"][0]["sample_count"] > 0 else
            "NO_SAMPLES" if len(mappings) == 1 else "AMBIGUOUS_MAPPING"
        )
        result.append(entry)
    return {
        "functions": result,
        "functions_with_samples": sum(x["temporal_coverage_status"] == "HAS_SAMPLES" for x in result),
        "functions_without_samples": sum(x["temporal_coverage_status"] == "NO_SAMPLES" for x in result),
        "ambiguous_functions": sum(x["temporal_coverage_status"] == "AMBIGUOUS_MAPPING" for x in result),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", default="reports/tep_nexus_temporal_coverage.json")
    args = parser.parse_args()
    run_id = str(UUID(args.run_id))
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")
    discovery = json.loads(Path(args.discovery).read_text(encoding="utf-8-sig"))
    if discovery.get("mapping_confidence") != "PROVISIONAL_NOT_PHYSICALLY_VERIFIED":
        parser.error("Unexpected discovery report confidence marker")
    signals = sorted({
        m["operational_signal"] for c in discovery["candidates"]
        for m in c["mappings"]
    })
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT signal_id, COUNT(*), MAX(simulation_time_hours)
                       FROM public.signal_samples
                       WHERE run_id = %s::uuid AND signal_id = ANY(%s::text[])
                       GROUP BY signal_id""",
                    (run_id, signals),
                )
                rows = cur.fetchall()
    report = {
        "interface": "TEP NEXUS TimescaleDB temporal coverage",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "run_identity_source": "operator_supplied",
        "shared_run_provenance": "NOT_VERIFIED",
        "physical_sensor_binding": "NOT_VERIFIED",
        "planner_allowlist_modified": False,
        **build_coverage(discovery, rows),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "functions_with_samples": report["functions_with_samples"],
        "functions_without_samples": report["functions_without_samples"],
        "ambiguous_functions": report["ambiguous_functions"],
        "run_id": run_id,
    }, indent=2))
    print("Saved:", output)


if __name__ == "__main__":
    main()
