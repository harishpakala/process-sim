"""TEP NEXUS v2: read-only cross-store validation."""

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


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def check_graphdb(url):
    response = requests.post(
        url,
        data={"query": SPARQL},
        headers={"Accept": "application/sparql-results+json"},
        timeout=20,
    )
    response.raise_for_status()

    bindings = response.json()["results"]["bindings"]
    rows = [
        {k: v["value"] for k, v in row.items()}
        for row in bindings
    ]

    valid = (
        len(rows) == 1
        and rows[0].get("signal") == "XMEAS9"
    )

    return {
        "status": "PASS_PROVISIONAL" if valid else "REVIEW_REQUIRED",
        "engineering_function": "TI_101",
        "mapping_status": "PROVISIONAL_ENGINEERING_MATCH",
        "matches": rows,
    }


async def read_opcua(client, time_node, signal_node):
    # One OPC UA service request, not an atomic simulator snapshot.
    values = await client.uaclient.read_attributes(
        [time_node.nodeid, signal_node.nodeid],
        ua.AttributeIds.Value,
    )

    if len(values) != 2:
        raise RuntimeError("Expected two OPC UA DataValues")

    clock, signal = values

    if not clock.StatusCode.is_good():
        raise RuntimeError(
            f"Bad simulation-clock quality: {clock.StatusCode}"
        )

    if not signal.StatusCode.is_good():
        raise RuntimeError(
            f"Bad XMEAS9 quality: {signal.StatusCode}"
        )

    return {
        "simulation_seconds": float(clock.Value.Value) * 3600,
        "value": float(signal.Value.Value),
        "quality": str(signal.StatusCode),
        "time_source_timestamp": str(clock.SourceTimestamp),
        "signal_source_timestamp": str(signal.SourceTimestamp),
        "read_at_utc": utc_now(),
    }


def query_nearby(dsn, run_id, seconds, window):
    # Round simulation seconds to avoid floating-point boundary
    # exclusions (for example, 1966.00000000001).
    sql = """
        SELECT
            simulation_time_hours * 3600 AS seconds,
            value,
            observed_at
        FROM public.signal_samples
        WHERE run_id = %s::uuid
          AND signal_id = 'XMEAS9'
          AND ROUND(
              (simulation_time_hours * 3600)::numeric, 6
          ) BETWEEN %s AND %s
        ORDER BY
            ABS(simulation_time_hours * 3600 - %s),
            observed_at DESC
        LIMIT 20
    """

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        run_id,
                        seconds - window,
                        seconds + window,
                        seconds,
                    ),
                )
                rows = cur.fetchall()

    return [
        {
            "simulation_seconds": float(row[0]),
            "value": float(row[1]),
            "observed_at": row[2].isoformat(),
        }
        for row in rows
    ]


def classify(opc, rows, time_tolerance, value_tolerance):
    if not rows:
        return {
            "status": "UNMATCHED",
            "reason": "No database sample in search window",
        }

    exact_time_rows = [
        row for row in rows
        if abs(
            row["simulation_seconds"] - opc["simulation_seconds"]
        ) <= time_tolerance
    ]

    exact_matches = [
        row for row in exact_time_rows
        if abs(row["value"] - opc["value"]) <= value_tolerance
    ]

    if exact_matches:
        selected = min(
            exact_matches,
            key=lambda row: abs(
                row["simulation_seconds"]
                - opc["simulation_seconds"]
            ),
        )
        status = "EXACT_TIME_AND_VALUE_MATCH"

    elif exact_time_rows:
        selected = min(
            exact_time_rows,
            key=lambda row: abs(
                row["value"] - opc["value"]
            ),
        )
        status = "TIME_MATCH_VALUE_DIFFERENT"

    else:
        selected = min(
            rows,
            key=lambda row: abs(
                row["simulation_seconds"]
                - opc["simulation_seconds"]
            ),
        )
        status = "NEARBY_SAMPLE_ONLY"

    return {
        "status": status,
        "database_sample": selected,
        "time_difference_seconds": abs(
            selected["simulation_seconds"]
            - opc["simulation_seconds"]
        ),
        "value_difference": abs(
            selected["value"] - opc["value"]
        ),
    }


async def validate_one(args, dsn, opc):
    last_result = None

    # Allow the asynchronous recorder to catch up.
    for attempt in range(args.retries + 1):
        if attempt > 0:
            await asyncio.sleep(args.retry_delay)

        rows = query_nearby(
            dsn,
            args.run_id,
            opc["simulation_seconds"],
            args.search_window,
        )

        result = classify(
            opc,
            rows,
            args.time_tolerance,
            args.value_tolerance,
        )

        result["database_query_attempts"] = attempt + 1
        last_result = result

        if result["status"] == "EXACT_TIME_AND_VALUE_MATCH":
            break

    return last_result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--observations", type=int, default=5)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--search-window", type=float, default=3.5)
    parser.add_argument("--time-tolerance", type=float, default=0.15)
    parser.add_argument("--value-tolerance", type=float, default=1e-9)
    parser.add_argument(
        "--endpoint",
        default="opc.tcp://127.0.0.1:4841/process-sim/",
    )
    parser.add_argument(
        "--graphdb-url",
        default=os.getenv(
            "TEP_GRAPHDB_URL",
            "http://localhost:7200/repositories/AAS",
        ),
    )
    parser.add_argument(
        "--output",
        default="reports/tep_nexus_validation_v2.json",
    )
    args = parser.parse_args()

    if (
        args.observations < 1
        or args.retries < 0
        or args.interval < 0
        or args.retry_delay < 0
        or args.search_window < 0
        or args.time_tolerance < 0
        or args.value_tolerance < 0
    ):
        parser.error("Invalid observation count or negative parameter")

    report = {
        "version": "2.0",
        "generated_at_utc": utc_now(),
        "run_id": args.run_id,
        "graphdb": None,
        "observations": [],
        "summary": {},
        "limitations": [
            "GraphDB engineering mapping is provisional.",
            "OPC UA and TimescaleDB shared run identity is unverified.",
            "The run ID is operator-supplied.",
            "OPC UA multi-node reads are not guaranteed atomic.",
            "Nearby samples are not exact measurement matches.",
            "A zero measurement may represent initialization.",
            "Only simulated, not physical, sensor connectivity is tested.",
        ],
    }

    try:
        dsn = os.getenv("TEP_TIMESCALE_DSN")
        if not dsn:
            raise RuntimeError("TEP_TIMESCALE_DSN is missing")

        report["graphdb"] = check_graphdb(args.graphdb_url)

        if report["graphdb"]["status"] != "PASS_PROVISIONAL":
            raise RuntimeError(
                "GraphDB mapping not uniquely verified"
            )

        async with Client(url=args.endpoint) as client:
            ns = await client.get_namespace_index(
                "urn:process-sim:opcua"
            )

            time_node = await client.nodes.objects.get_child([
                f"{ns}:TEP",
                f"{ns}:Simulation",
                f"{ns}:TimeHours",
            ])

            signal_node = client.get_node(
                f"ns={ns};s=TEP.Measurements.XMEAS9"
            )

            for index in range(args.observations):
                if index > 0:
                    await asyncio.sleep(args.interval)

                opc = await read_opcua(
                    client, time_node, signal_node
                )

                comparison = await validate_one(
                    args, dsn, opc
                )

                item = {
                    "observation": index + 1,
                    "opcua": opc,
                    "comparison": comparison,
                }

                report["observations"].append(item)

                print(
                    f"Observation {index + 1}: "
                    f"{comparison['status']} "
                    f"at {opc['simulation_seconds']:.3f}s",
                    flush=True,
                )

        statuses = [
            item["comparison"]["status"]
            for item in report["observations"]
        ]

        report["summary"] = {
            "status": "COMPLETED",
            "total_observations": len(statuses),
            "exact_matches": statuses.count(
                "EXACT_TIME_AND_VALUE_MATCH"
            ),
            "time_match_value_different": statuses.count(
                "TIME_MATCH_VALUE_DIFFERENT"
            ),
            "nearby_samples": statuses.count(
                "NEARBY_SAMPLE_ONLY"
            ),
            "unmatched": statuses.count("UNMATCHED"),
            "shared_run_provenance": "NOT_VERIFIED",
        }

    except Exception as exc:
        report["summary"] = {
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "completed_observations": len(
                report["observations"]
            ),
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nSUMMARY")
    print(json.dumps(report["summary"], indent=2))
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    asyncio.run(main())
