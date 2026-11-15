"""Read-only DEXPI -> OPCUAConnectivity -> TimescaleDB historian CLI.

This is an independent semantic-historian path. It does not assert
AssetInventory relationships or physical sensor provenance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
import requests

FUNCTION_RE = re.compile(r"^[A-Za-z]{2}_\d+$")
QUESTION_FUNCTION_RE = re.compile(r"\b[A-Za-z]{2}_\d+\b", re.I)

SPARQL = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX opcua: <https://example.org/opcuaconnectivity/>
SELECT DISTINCT ?assetIdentifier ?signalName WHERE {
  GRAPH ?dexpiGraph {
    ?function a dexpi:InstrumentationFunction ;
              dexpi:hasLocalId ?localId ;
              dexpi:hasAssetIdentifier ?assetIdentifier .
  }
  GRAPH ?opcuaGraph {
    ?mapping opcua:hasAssetIdentifier ?assetIdentifier ;
             opcua:hasSignalName ?signalName .
  }
  FILTER(STR(?localId) = %s)
}
ORDER BY ?assetIdentifier ?signalName
"""


def resolve_signal(graphdb_url, function, *, domain="DEXPI", post=requests.post):
    if domain not in ("DEXPI", "ECAD"):
        raise ValueError("Unsupported domain")
    pattern = FUNCTION_RE if domain == "DEXPI" else re.compile(r"^(?:FI|LI|PI|TI)-[0-9]+$")
    if not pattern.fullmatch(function):
        raise ValueError("Invalid engineering function LocalId")
    # JSON-quoted literal prevents SPARQL injection; the function is additionally allow-pattern checked.
    query = SPARQL % json.dumps(function)
    if domain == "ECAD":
        query = """
PREFIX ecad: <https://example.org/ecad/>
PREFIX opcua: <https://example.org/opcuaconnectivity/>
SELECT DISTINCT ?assetIdentifier ?signalName WHERE {
 GRAPH ?eg {
  ?component ecad:hasLocalId ?localId ;
             ecad:hasAssetIdentifier ?assetIdentifier .
 }
 GRAPH ?og {
  ?mapping opcua:hasAssetIdentifier ?assetIdentifier ;
           opcua:hasSignalName ?signalName .
 }
 FILTER(STR(?localId) = %s)
} ORDER BY ?assetIdentifier ?signalName
""" % json.dumps(function)
    response = post(
        graphdb_url, data={"query": query},
        headers={"Accept": "application/sparql-results+json"}, timeout=30,
    )
    response.raise_for_status()
    pairs = set()
    for row in response.json()["results"]["bindings"]:
        asset = row["assetIdentifier"]["value"].strip()
        signal = row["signalName"]["value"].strip()
        if not asset or not signal:
            raise ValueError("GraphDB returned an empty mapping field")
        pairs.add((asset, signal))
    if len(pairs) != 1:
        raise RuntimeError(
            f"Expected exactly one live {domain}/OPCUAConnectivity mapping for {function}; "
            f"found {len(pairs)} distinct mappings"
        )
    asset, signal = next(iter(pairs))
    return {"engineering_function": function, "asset_identifier": asset,
            "operational_signal": signal,
            "resolution_method": f"live {domain}/OPCUAConnectivity hasAssetIdentifier equality",
            "physical_sensor_binding": "NOT_VERIFIED"}


def retrieve(dsn, run_id, signal, start_seconds=None, end_seconds=None, *,
             connection_factory=psycopg.connect):
    clauses = ["run_id = %s::uuid", "signal_id = %s"]
    params = [run_id, signal]
    if start_seconds is not None:
        clauses.append("simulation_time_hours >= %s")
        params.append(start_seconds / 3600.0)
    if end_seconds is not None:
        clauses.append("simulation_time_hours <= %s")
        params.append(end_seconds / 3600.0)
    sql = (
        "SELECT simulation_time_hours, value, observed_at "
        "FROM public.signal_samples WHERE " + " AND ".join(clauses) +
        " ORDER BY simulation_time_hours, observed_at, value"
    )
    with connection_factory(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    samples = []
    for hours, value, observed_at in rows:
        if not math.isfinite(float(hours)) or not math.isfinite(float(value)):
            raise ValueError("Non-finite historian observation")
        samples.append({"simulationTimeHours": float(hours), "value": float(value),
                        "observedAt": observed_at.isoformat()})
    return samples


def execute(question, function, run_id, dsn, graphdb_url,
            start_seconds=None, end_seconds=None, *,
            resolver=resolve_signal, retriever=retrieve, domain="DEXPI"):
    if domain not in ("DEXPI", "ECAD"):
        raise ValueError("Unsupported domain")
    function = function.upper()
    run_id = str(UUID(str(run_id)))
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question is required")
    id_pattern = re.compile(r"(?<![A-Za-z0-9_-])(?:[A-Za-z]{2}[_-][0-9]+)(?![A-Za-z0-9_-])", re.I)
    mentioned = {x.upper() for x in id_pattern.findall(question)}
    if mentioned != {function}:
        raise ValueError("Question and requested engineering function must agree")
    for bound in (start_seconds, end_seconds):
        if bound is not None and (isinstance(bound, bool)
                                  or not isinstance(bound, (int, float))
                                  or not math.isfinite(bound) or bound < 0):
            raise ValueError("Optional simulation-second bounds must be nonnegative finite numbers")
    if start_seconds is not None and end_seconds is not None and start_seconds > end_seconds:
        raise ValueError("Start time must not exceed end time")
    mapping = (resolver(graphdb_url, function) if domain == "DEXPI"
               else resolver(graphdb_url, function, domain=domain))
    if mapping["engineering_function"] != function:
        raise ValueError("Resolved function differs from requested function")
    samples = retriever(dsn, run_id, mapping["operational_signal"],
                        start_seconds, end_seconds)
    return {
        "interface": "TEP NEXUS DEXPI/OPCUAConnectivity historian query v1",
        "question": question, "engineeringFunction": function, "domain": domain, "runId": run_id,
        "mapping": mapping, "timeBasis": "simulation_time",
        "startSimulationSeconds": start_seconds,
        "endSimulationSeconds": end_seconds,
        "observationCount": len(samples), "truncated": False,
        "observations": samples, "materializedInGraphDB": False,
        "provenance": {
            "semanticSource": f"live GraphDB {domain} and OPCUAConnectivity",
            "temporalSource": "TimescaleDB public.signal_samples",
            "physicalSensorBinding": "NOT_VERIFIED",
            "sharedRunProvenance": "NOT_VERIFIED",
        },
        "retrievedAtUtc": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--domain", choices=("DEXPI", "ECAD"), default="DEXPI")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--output", default="reports/tep_nexus_dexpi_historian.json")
    args = parser.parse_args()
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")
    result = execute(args.question, args.function, args.run_id, dsn,
                     args.graphdb_url, args.start_seconds, args.end_seconds,
                     domain=args.domain)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output),
                      "engineeringFunction": result["engineeringFunction"],
                      "signal": result["mapping"]["operational_signal"],
                      "observationCount": result["observationCount"],
                      "truncated": result["truncated"]}, indent=2))


if __name__ == "__main__":
    main()
