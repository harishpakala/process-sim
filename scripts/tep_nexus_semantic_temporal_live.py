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
PREFIX dx: <https://example.org/dexpi/>
PREFIX ec: <https://example.org/ecad/>
PREFIX ai: <https://example.org/assetinventory/>
PREFIX pc: <https://example.org/productcatalog/>
SELECT DISTINCT ?assetId ?dexpiLocal ?ecadLocal ?signal ?productId ?eclassCode WHERE {
  ?d dx:hasAssetIdentifier ?assetId ;
     dx:hasLocalId ?dexpiLocal .
  FILTER(STR(?assetId) = STR(?requestedAsset))
  ?e ec:hasAssetIdentifier ?ecadId ;
     ec:hasLocalId ?ecadLocal .
  ?a ai:hasAssetIdentifier ?inventoryId ;
     ai:hasOperationalReference ?signal ;
     ai:hasProductIdentifier ?productId .
  ?p pc:hasProductIdentifier ?catalogId .
  OPTIONAL { ?p pc:hasECLASSClass ?eclassCode }
  FILTER(STR(?assetId) = STR(?ecadId) &&
         STR(?assetId) = STR(?inventoryId) &&
         STR(?productId) = STR(?catalogId))
}
"""

def now_utc():
    return datetime.now(timezone.utc)


def resolve_engineering_context(graphdb_url, asset_identifier):
    # Bind as a SPARQL literal; identifiers in the lifted graph are literals.
    literal = json.dumps(asset_identifier)
    query = SPARQL.replace("?requestedAsset", literal)
    response = requests.post(
        graphdb_url,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=20,
    )
    response.raise_for_status()
    rows = [
        {key: value["value"] for key, value in row.items()}
        for row in response.json()["results"]["bindings"]
    ]
    if len(rows) != 1:
        raise RuntimeError(
            f"Expected exactly one four-domain mapping for {asset_identifier}; "
            f"found {len(rows)}"
        )
    row = rows[0]
    return {
        "asset_identifier": row["assetId"],
        "dexpi_local_id": row["dexpiLocal"],
        "ecad_local_id": row["ecadLocal"],
        "operational_signal": row["signal"],
        "product_identifier": row["productId"],
        "eclass_code": row.get("eclassCode"),
        "mapping_status": "ACCEPTED_LOGICAL_SIMULATION_IDENTITY",
        "physical_installation_verified": False,
        "mapping_source": "GraphDB AAS repository",
        "resolution_method": "four-domain AssetIdentifier/ProductIdentifier SPARQL join",
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
        "evaluation": "E2 engineering-to-operational evidence retrieval",
        "generated_at_utc": now_utc().isoformat(),
        "query": {
            "asset_identifier": args.asset_identifier,
            "requested_history_minutes": args.window_minutes,
        },
        "engineering_context": mapping,
        "temporal_context": temporal,
        "evidence_path": [
            {"source": "GraphDB", "relationship": "DEXPI/ECAD/AssetInventory shared logical AssetIdentifier",
             "identifier": mapping["asset_identifier"]},
            {"source": "GraphDB", "relationship": "AssetInventory to ProductCatalog ProductIdentifier",
             "identifier": mapping["product_identifier"]},
            {"source": "GraphDB", "relationship": "AssetInventory OperationalReference",
             "identifier": mapping["operational_signal"]},
            {"source": "TimescaleDB", "relationship": "run ID + signal to timestamped measurements",
             "identifier": args.run_id},
        ],
        "limitations": [
            "Logical simulation identity is accepted for the selected asset; physical installation is not verified.",
            "Product associations are candidates, not verified physical installations.",
            "ECLASS values are graph metadata, not independently certified classifications.",
            "Run ID is operator supplied; shared OPC UA/TimescaleDB provenance is not independently verified.",
            "Measurements are stored in TimescaleDB, not materialized as RDF.",
            "Retrieval is evidence access, not fault diagnosis or causal inference.",
        ],
    }


def print_summary(report):
    mapping = report["engineering_context"]
    temporal = report["temporal_context"]

    print("\n=== TEP NEXUS SEMANTIC-TEMPORAL QUERY ===")
    print("Engineering function:", mapping["dexpi_local_id"])
    print("AAS function reference:", mapping["asset_identifier"])
    print("Operational signal:", mapping["operational_signal"])
    print("Asset URI:", mapping["asset_identifier"])
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
    parser.add_argument("--asset-identifier", default="https://aas.example.com/PI101")
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
        default="reports/tep_nexus_e2_evidence.json",
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
    mapping = resolve_engineering_context(args.graphdb_url, args.asset_identifier)

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
