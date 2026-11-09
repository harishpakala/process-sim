"""Read-only TEP NEXUS cross-store measurement validator."""

# Created: 2026-11-01
# Author: Harish

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from asyncua import Client, ua


GRAPHDB_QUERY = """
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
      STR(?refPath),
      ".EngineeringFunctionReference"
    ) AS ?mappingPath
  )

  FILTER(
    STR(?signalPath) =
    CONCAT(?mappingPath, ".SignalName")
  )

  ?asset inv:hasOperationalReference ?signal .
}
"""


def graphdb_evidence(url):
    response = requests.post(
        url,
        data={"query": GRAPHDB_QUERY},
        headers={"Accept": "application/sparql-results+json"},
        timeout=20,
    )
    response.raise_for_status()

    rows = response.json()["results"]["bindings"]
    matches = [
        {key: value["value"] for key, value in row.items()}
        for row in rows
    ]

    if len(matches) != 1 or matches[0].get("signal") != "XMEAS9":
        return {
            "status": "REVIEW_REQUIRED",
            "matching_rows": matches,
        }

    return {
        "status": "PASS_PROVISIONAL",
        "engineering_function": "TI_101",
        "mapping_status": "PROVISIONAL_ENGINEERING_MATCH",
        **matches[0],
    }


async def opcua_evidence(endpoint, namespace):
    async with Client(url=endpoint) as client:
        ns = await client.get_namespace_index(namespace)

        time_node = await client.nodes.objects.get_child([
            f"{ns}:TEP",
            f"{ns}:Simulation",
            f"{ns}:TimeHours",
        ])

        signal_node = client.get_node(
            f"ns={ns};s=TEP.Measurements.XMEAS9"
        )

        # One OPC UA Read request for both variables.
        # This does not guarantee an atomic simulator snapshot.
        results = await client.uaclient.read_attributes(
            [time_node.nodeid, signal_node.nodeid],
            ua.AttributeIds.Value,
        )

        if len(results) != 2:
            raise RuntimeError("Expected two OPC UA DataValues")

        time_dv, signal_dv = results

        if (
            not time_dv.StatusCode.is_good()
            or not signal_dv.StatusCode.is_good()
        ):
            return {
                "status": "BAD_QUALITY",
                "time_quality": str(time_dv.StatusCode),
                "signal_quality": str(signal_dv.StatusCode),
            }

        return {
            "status": "GOOD",
            "simulation_seconds": float(time_dv.Value.Value) * 3600,
            "signal": "XMEAS9",
            "value": float(signal_dv.Value.Value),
            "time_source_timestamp": str(time_dv.SourceTimestamp),
            "signal_source_timestamp": str(signal_dv.SourceTimestamp),
            "signal_quality": str(signal_dv.StatusCode),
            "read_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_method": "single OPC UA Read request; not guaranteed atomic",
        }


def timescaledb_evidence(dsn, run_id, target_seconds, tolerance):
    sql = """
        SELECT
            simulation_time_hours * 3600 AS seconds,
            value,
            observed_at
        FROM public.signal_samples
        WHERE run_id = %s::uuid
          AND signal_id = 'XMEAS9'
          AND simulation_time_hours * 3600
              BETWEEN %s AND %s
        ORDER BY
            ABS(simulation_time_hours * 3600 - %s),
            observed_at DESC
        LIMIT 1
    """

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        run_id,
                        target_seconds - tolerance,
                        target_seconds + tolerance,
                        target_seconds,
                    ),
                )
                row = cur.fetchone()

    if row is None:
        return {
            "status": "NO_MATCHING_TIME",
            "run_id": run_id,
            "time_tolerance_seconds": tolerance,
        }

    return {
        "status": "FOUND",
        "run_id": run_id,
        "signal": "XMEAS9",
        "simulation_seconds": float(row[0]),
        "value": float(row[1]),
        "observed_at": row[2].isoformat(),
        "time_tolerance_seconds": tolerance,
    }


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--endpoint",
        default="opc.tcp://127.0.0.1:4841/process-sim/",
    )
    parser.add_argument(
        "--namespace",
        default="urn:process-sim:opcua",
    )
    parser.add_argument(
        "--graphdb-url",
        default=os.getenv(
            "TEP_GRAPHDB_URL",
            "http://localhost:7200/repositories/AAS",
        ),
    )
    parser.add_argument("--time-tolerance", type=float, default=2.0)
    parser.add_argument("--value-tolerance", type=float, default=1e-9)
    parser.add_argument(
        "--output",
        default="reports/tep_nexus_cross_store_validation.json",
    )

    args = parser.parse_args()

    if args.time_tolerance < 0 or args.value_tolerance < 0:
        parser.error("Tolerances must be nonnegative")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "read-only simulated measurement correspondence",
        "graphdb": None,
        "opcua": None,
        "timescaledb": None,
        "comparison": {"status": "NOT_EVALUATED"},
        "limitations": [
            "Engineering mapping is provisional, not physically validated.",
            "Shared OPC UA and TimescaleDB run identity is not verified.",
            "The TimescaleDB run ID is supplied by the operator.",
            "Multi-node OPC UA reads are not guaranteed atomic.",
            "Matching values do not prove physical sensor connectivity.",
            "An initial zero may represent simulator initialization.",
        ],
    }

    try:
        report["graphdb"] = graphdb_evidence(args.graphdb_url)

        if report["graphdb"]["status"] != "PASS_PROVISIONAL":
            report["comparison"] = {
                "status": "BLOCKED_GRAPH_MAPPING"
            }

        else:
            report["opcua"] = await opcua_evidence(
                args.endpoint,
                args.namespace,
            )

            if report["opcua"]["status"] != "GOOD":
                report["comparison"] = {
                    "status": "BLOCKED_OPCUA_QUALITY"
                }

            else:
                dsn = os.getenv("TEP_TIMESCALE_DSN")

                if not dsn:
                    raise RuntimeError(
                        "TEP_TIMESCALE_DSN environment variable is missing"
                    )

                report["timescaledb"] = timescaledb_evidence(
                    dsn,
                    args.run_id,
                    report["opcua"]["simulation_seconds"],
                    args.time_tolerance,
                )

                db = report["timescaledb"]

                if db["status"] == "FOUND":
                    delta_time = abs(
                        db["simulation_seconds"]
                        - report["opcua"]["simulation_seconds"]
                    )

                    delta_value = abs(
                        db["value"] - report["opcua"]["value"]
                    )

                    matched = (
                        delta_time <= 0.15
                        and delta_value <= args.value_tolerance
                    )

                    report["comparison"] = {
                        "status": (
                            "VALUE_AND_TIME_MATCH"
                            if matched
                            else "NEAREST_SAMPLE_ONLY"
                        ),
                        "absolute_time_difference_seconds": delta_time,
                        "absolute_value_difference": delta_value,
                        "value_tolerance": args.value_tolerance,
                        "same_run_provenance": "NOT_VERIFIED",
                    }

                else:
                    report["comparison"] = {
                        "status": "NO_MATCHING_DB_SAMPLE",
                        "same_run_provenance": "NOT_VERIFIED",
                    }

    except Exception as exc:
        report["comparison"] = {
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(f"\nSaved report: {output}")


if __name__ == "__main__":
    asyncio.run(main())
