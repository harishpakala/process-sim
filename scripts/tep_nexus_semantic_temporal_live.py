"""TEP NEXUS: semantic-temporal live query demonstrator.

Read-only integration:
DEXPI engineering function -> AAS mapping -> AssetInventory asset
-> TimescaleDB latest measurement and simulation-time history.
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests


SPARQL = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX inv: <https://example.org/assetinventory/>
PREFIX aas: <https://example.org/aas/>

SELECT DISTINCT ?functionRef ?signal ?asset WHERE {
  ?function dexpi:hasLocalId "TI_101" ;
            dexpi:hasAssetIdentifier ?functionRef .
  ?mappingRef aas:value ?functionRef ;
              aas:elementPath ?refPath .
  ?signalNode aas:value ?signal ;
              aas:elementPath ?signalPath .

  BIND(
    STRBEFORE(
      STR(?refPath), ".EngineeringFunctionReference"
    ) AS ?mappingPath
  )

  FILTER(
    STR(?signalPath) =
    CONCAT(?mappingPath, ".SignalName")
  )

  ?asset inv:hasOperationalReference ?signal .
}
"""


def now_utc():
    return datetime.now(timezone.utc)


def resolve_engineering_context(graphdb_url):
    response = requests.post(
        graphdb_url,
        data={"query": SPARQL},
        headers={"Accept": "application/sparql-results+json"},
        timeout=20,
    )
    response.raise_for_status()

    bindings = response.json()["results"]["bindings"]

    rows = [
        {key: value["value"] for key, value in row.items()}
        for row in bindings
    ]

    if len(rows) != 1:
        raise RuntimeError(
            f"Expected one engineering mapping; found {len(rows)}"
        )

    mapping = rows[0]

    if mapping["signal"] != "XMEAS9":
        raise RuntimeError(
            "Unexpected signal for verified TI_101 mapping: "
            + mapping["signal"]
        )

    return {
        "engineering_function": "TI_101",
        "function_reference": mapping["functionRef"],
        "operational_signal": mapping["signal"],
        "asset_uri": mapping["asset"],
        "mapping_status": "PROVISIONAL_ENGINEERING_MATCH",
        "mapping_source": "GraphDB AAS repository",
        "resolution_method": "path-constrained SPARQL",
    }


def retrieve_temporal_context(
    dsn, run_id, signal, window_minutes, history_limit
):
    latest_sql = """
        SELECT
            simulation_time_hours,
            value,
            observed_at
        FROM public.signal_samples
        WHERE run_id = %s::uuid
          AND signal_id = %s
        ORDER BY simulation_time_hours DESC, observed_at DESC
        LIMIT 1
    """

    history_sql = """
        SELECT
            simulation_time_hours,
            value,
            observed_at
        FROM public.signal_samples
        WHERE run_id = %s::uuid
          AND signal_id = %s
          AND simulation_time_hours >= %s
          AND simulation_time_hours <= %s
        ORDER BY simulation_time_hours DESC, observed_at DESC
        LIMIT %s
    """

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")

            with conn.cursor() as cur:
                cur.execute(latest_sql, (run_id, signal))
                latest = cur.fetchone()

                if latest is None:
                    return {
                        "status": "NO_SAMPLES",
                        "run_id": run_id,
                        "signal": signal,
                    }

                latest_hours = float(latest[0])
                lower_hours = latest_hours - window_minutes / 60.0

                cur.execute(
                    history_sql,
                    (
                        run_id,
                        signal,
                        lower_hours,
                        latest_hours,
                        history_limit,
                    ),
                )
                history_rows = cur.fetchall()

    observed_at = latest[2]
    age_seconds = (
        now_utc() - observed_at.astimezone(timezone.utc)
    ).total_seconds()

    history = [
        {
            "simulation_seconds": round(float(row[0]) * 3600, 6),
            "value": float(row[1]),
            "observed_at": row[2].isoformat(),
        }
        for row in reversed(history_rows)
    ]

    values = [item["value"] for item in history]

    return {
        "status": "AVAILABLE",
        "run_id": run_id,
        "run_identity_source": "operator_supplied",
        "signal": signal,
        "latest": {
            "simulation_seconds": round(latest_hours * 3600, 6),
            "value": float(latest[1]),
            "observed_at": observed_at.isoformat(),
            "record_age_seconds": round(age_seconds, 3),
        },
        "history": {
            "window_basis": "simulation_time",
            "requested_window_minutes": window_minutes,
            "returned_samples": len(history),
            "history_limit": history_limit,
            "truncated_by_limit": len(history) >= history_limit,
            "minimum": min(values),
            "maximum": max(values),
            "first": history[0],
            "last": history[-1],
            "samples": history,
        },
    }


def make_report(args, mapping, temporal):
    return {
        "demonstrator": "TEP NEXUS semantic-temporal query",
        "generated_at_utc": now_utc().isoformat(),
        "query": {
            "engineering_function": "TI_101",
            "requested_history_minutes": args.window_minutes,
        },
        "engineering_context": mapping,
        "temporal_context": temporal,
        "evidence_path": [
            {
                "source": "GraphDB",
                "relationship": "DEXPI engineering function -> AAS function reference",
                "identifier": mapping["function_reference"],
            },
            {
                "source": "GraphDB",
                "relationship": "AAS mapping -> operational signal",
                "identifier": mapping["operational_signal"],
            },
            {
                "source": "GraphDB",
                "relationship": "operational reference -> AssetInventory asset",
                "identifier": mapping["asset_uri"],
            },
            {
                "source": "TimescaleDB",
                "relationship": "signal + run ID -> time-indexed observations",
                "identifier": args.run_id,
            },
        ],
        "limitations": [
            "Engineering-to-operational mapping is provisional.",
            "Run ID is supplied by the operator.",
            "Shared OPC UA/TimescaleDB run provenance is not verified.",
            "Temporal observations remain in TimescaleDB; "
            "this is a federated semantic-temporal query, "
            "not proof that observations are materialized as RDF.",
            "Data freshness describes the latest persisted record, "
            "not an independently verified physical sensor reading.",
            "TEP simulation is an experimental data source, "
            "not a validated physical plant model.",
        ],
    }


def print_summary(report):
    mapping = report["engineering_context"]
    temporal = report["temporal_context"]

    print("\n=== TEP NEXUS SEMANTIC-TEMPORAL QUERY ===")
    print("Engineering function:", mapping["engineering_function"])
    print("AAS function reference:", mapping["function_reference"])
    print("Operational signal:", mapping["operational_signal"])
    print("Asset URI:", mapping["asset_uri"])
    print("Mapping status:", mapping["mapping_status"])

    if temporal["status"] != "AVAILABLE":
        print("Temporal status:", temporal["status"])
        return

    latest = temporal["latest"]
    history = temporal["history"]

    print("\nLatest persisted measurement")
    print("Simulation time (s):", latest["simulation_seconds"])
    print("Value:", latest["value"])
    print("Recorded at:", latest["observed_at"])
    print("Record age (s):", latest["record_age_seconds"])

    print("\nRecent simulation-time history")
    print("Window (minutes):", history["requested_window_minutes"])
    print("Samples returned:", history["returned_samples"])
    print("Minimum:", history["minimum"])
    print("Maximum:", history["maximum"])
    print("History truncated:", history["truncated_by_limit"])

    print("\nEvidence: GraphDB -> signal -> TimescaleDB")
    print("Shared run provenance: NOT VERIFIED")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-minutes", type=float, default=10)
    parser.add_argument("--history-limit", type=int, default=1000)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--iterations", type=int, default=5)

    parser.add_argument(
        "--graphdb-url",
        default=os.getenv(
            "TEP_GRAPHDB_URL",
            "http://localhost:7200/repositories/AAS",
        ),
    )
    parser.add_argument(
        "--output",
        default="reports/tep_nexus_semantic_temporal_live.json",
    )

    args = parser.parse_args()

    if (
        args.window_minutes <= 0
        or args.history_limit < 1
        or args.interval <= 0
        or args.iterations < 1
    ):
        parser.error("Window, history limit, interval and iterations must be positive")

    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")

    # Resolve engineering semantics once, then refresh temporal data.
    mapping = resolve_engineering_context(args.graphdb_url)

    repetitions = args.iterations if args.watch else 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    for index in range(repetitions):
        temporal = retrieve_temporal_context(
            dsn,
            args.run_id,
            mapping["operational_signal"],
            args.window_minutes,
            args.history_limit,
        )

        report = make_report(args, mapping, temporal)
        print_summary(report)

        output.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        print("\nSaved:", output)

        if index < repetitions - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
