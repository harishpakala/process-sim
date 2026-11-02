"""TEP NEXUS: read-only virtual temporal knowledge graph interface."""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import psycopg
import requests


def resolve_mapping(endpoint, function_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", function_id):
        raise ValueError("Invalid engineering function identifier")

    # JSON string syntax is compatible with SPARQL quoted strings.
    function_literal = json.dumps(function_id)

    query = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX inv: <https://example.org/assetinventory/>
PREFIX aas: <https://example.org/aas/>

SELECT DISTINCT ?functionRef ?signal ?asset WHERE {
  ?function dexpi:hasLocalId FUNCTION_ID ;
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
""".replace("FUNCTION_ID", function_literal)

    response = requests.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=20,
    )
    response.raise_for_status()

    rows = [
        {key: item["value"] for key, item in row.items()}
        for row in response.json()["results"]["bindings"]
    ]

    if len(rows) != 1:
        raise RuntimeError(
            f"Expected one unambiguous mapping for {function_id}; "
            f"found {len(rows)}"
        )

    return rows[0]


def fetch_history(dsn, run_id, signal, minutes, limit):
    sql = """
WITH latest AS (
    SELECT MAX(simulation_time_hours) AS latest_hours
    FROM public.signal_samples
    WHERE run_id = %s::uuid
      AND signal_id = %s
)
SELECT
    s.simulation_time_hours,
    s.value,
    s.observed_at
FROM public.signal_samples AS s
CROSS JOIN latest AS l
WHERE s.run_id = %s::uuid
  AND s.signal_id = %s
  AND s.simulation_time_hours >=
      l.latest_hours - (%s::double precision / 60.0)
  AND s.simulation_time_hours <= l.latest_hours
ORDER BY
    s.simulation_time_hours DESC,
    s.observed_at DESC
LIMIT %s
"""

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (run_id, signal, run_id, signal, minutes, limit),
                )
                rows = cur.fetchall()

    return [
        {
            "simulation_seconds": round(float(row[0]) * 3600, 6),
            "value": float(row[1]),
            "observed_at": row[2].isoformat(),
        }
        for row in rows
    ]


def build_graph(function_id, mapping, run_id, samples):
    base = "urn:tep-nexus:"
    function_node = base + "engineering:" + quote(function_id, safe="")
    signal_node = base + "signal:" + quote(mapping["signal"], safe="")
    run_node = base + "run:" + run_id

    nodes = [
        {
            "id": function_node,
            "type": "EngineeringFunction",
            "localId": function_id,
            "mappingStatus": "PROVISIONAL_ENGINEERING_MATCH",
        },
        {
            "id": mapping["functionRef"],
            "type": "AASFunctionReference",
        },
        {
            "id": signal_node,
            "type": "OperationalSignal",
            "signalId": mapping["signal"],
        },
        {
            "id": mapping["asset"],
            "type": "AssetInventoryAsset",
        },
        {
            "id": run_node,
            "type": "SimulationRunReference",
            "runId": run_id,
            "identitySource": "operator_supplied",
            "sharedRunProvenance": "NOT_VERIFIED",
        },
    ]

    edges = [
        {
            "source": function_node,
            "predicate": "hasAASFunctionReference",
            "target": mapping["functionRef"],
            "evidenceSource": "GraphDB",
        },
        {
            "source": mapping["functionRef"],
            "predicate": "mapsToOperationalSignal",
            "target": signal_node,
            "evidenceSource": "GraphDB",
        },
        {
            "source": signal_node,
            "predicate": "hasAssociatedAsset",
            "target": mapping["asset"],
            "evidenceSource": "GraphDB",
            "mappingStatus": "PROVISIONAL_ENGINEERING_MATCH",
        },
    ]

    for index, sample in enumerate(samples):
        # These are query-result node identifiers, not persistent
        # RDF observation identities.
        observation_node = (
            base + "query-observation:" + run_id + ":" + str(index)
        )

        nodes.append({
            "id": observation_node,
            "type": "TemporalObservation",
            "signalId": mapping["signal"],
            "value": sample["value"],
            "simulationTimeSeconds": sample["simulation_seconds"],
            "recordedAt": sample["observed_at"],
            "evidenceSource": "TimescaleDB",
            "queryResultIdentity": True,
        })

        edges.extend([
            {
                "source": signal_node,
                "predicate": "hasTemporalObservation",
                "target": observation_node,
                "evidenceSource": "TimescaleDB",
            },
            {
                "source": observation_node,
                "predicate": "retrievedUsingRunReference",
                "target": run_node,
                "evidenceSource": "operator_supplied_run_filter",
            },
        ])

    return {"nodes": nodes, "edges": edges}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", default="TI_101")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-minutes", type=float, default=10)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--graphdb-url",
        default=os.getenv(
            "TEP_GRAPHDB_URL",
            "http://localhost:7200/repositories/AAS",
        ),
    )
    parser.add_argument(
        "--output",
        default="reports/tep_nexus_virtual_temporal_kg.json",
    )
    args = parser.parse_args()

    if args.window_minutes <= 0 or args.limit < 1:
        parser.error("Window and limit must be positive")

    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")

    mapping = resolve_mapping(args.graphdb_url, args.function)

    samples = fetch_history(
        dsn,
        args.run_id,
        mapping["signal"],
        args.window_minutes,
        args.limit,
    )

    graph = build_graph(
        args.function, mapping, args.run_id, samples
    )

    latest = samples[0] if samples else None

    report = {
        "interface": "TEP NEXUS Virtual Temporal KG",
        "representation": "query-time property graph JSON",
        "generatedAtUTC": datetime.now(
            timezone.utc
        ).isoformat(),
        "query": {
            "engineeringFunction": args.function,
            "historyWindowSimulationMinutes": args.window_minutes,
            "runId": args.run_id,
        },
        "resolvedContext": {
            "aasFunctionReference": mapping["functionRef"],
            "operationalSignal": mapping["signal"],
            "assetURI": mapping["asset"],
            "mappingStatus": "PROVISIONAL_ENGINEERING_MATCH",
        },
        "latestPersistedObservation": latest,
        "observationCount": len(samples),
        "historyLimitReached": len(samples) >= args.limit,
        "graph": graph,
        "limitations": [
            "Graph relationships are assembled at query time.",
            "Observations are not asserted to exist as RDF in GraphDB.",
            "Observation node identifiers are local to this query result.",
            "Engineering mapping is provisional.",
            "Run ID is operator-supplied; shared provenance is unverified.",
            "Latest means latest persisted observation in the selected run.",
            "This does not validate physical process or sensor fidelity.",
        ],
    }

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n=== TEP NEXUS VIRTUAL TEMPORAL KG ===")
    print("Engineering function:", args.function)
    print("Operational signal:", mapping["signal"])
    print("Asset:", mapping["asset"])
    print("Mapping: PROVISIONAL_ENGINEERING_MATCH")
    print("Observations:", len(samples))
    print("Graph nodes:", len(graph["nodes"]))
    print("Graph edges:", len(graph["edges"]))
    print("Latest persisted observation:", latest)
    print("Shared run provenance: NOT VERIFIED")
    print("Saved:", path)


if __name__ == "__main__":
    main()
