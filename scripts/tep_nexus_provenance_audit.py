"""Read-only engineering mapping and historian provenance audit for TEP NEXUS.

GraphDB path-matching establishes candidate semantic links, not physical binding.
TimescaleDB run/signal presence establishes database co-occurrence, not a
cross-source shared-run origin or sensor installation provenance.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
import requests

from tep_nexus_function_registry import load_supported_functions
from tep_nexus_mapping_discovery import SPARQL, classify_bindings

SQL = """
SELECT signal_id, COUNT(*)::bigint, MIN(simulation_time_hours),
       MAX(simulation_time_hours)
FROM public.signal_samples
WHERE run_id = %s::uuid AND signal_id = ANY(%s::text[])
GROUP BY signal_id
ORDER BY signal_id
"""


def classify_evidence(registry, live, counts, run_id):
    """Classify explicit evidence; do not infer physical or shared-run provenance."""
    results = []
    for function, expected in sorted(registry.items()):
        candidates = [x for x in live["candidates"] if x["engineering_function"] == function]
        unique = (len(candidates) == 1
                  and candidates[0]["status"] == "UNIQUE_PROVISIONAL_CANDIDATE"
                  and len(candidates[0]["mappings"]) == 1)
        actual = candidates[0]["mappings"][0] if unique else None
        mapping_matches = actual == expected
        signal = expected["operational_signal"]
        historian = counts.get(signal)
        results.append({
            "engineeringFunction": function,
            "expectedMapping": expected,
            "graphdbMapping": actual,
            "graphdbMappingMatchesRegistry": mapping_matches,
            "historianRunSignalPresent": bool(historian and historian["sampleCount"] > 0),
            "historian": historian,
            "evidence": {
                "engineeringReferenceAndAasPathMatch": "SOURCE_QUERY_CONFIRMED" if mapping_matches else "NOT_CONFIRMED",
                "assetOperationalReferenceMatch": "SOURCE_QUERY_CONFIRMED" if mapping_matches else "NOT_CONFIRMED",
                "historianRunSignalCooccurrence": "SOURCE_QUERY_CONFIRMED" if historian and historian["sampleCount"] > 0 else "NOT_CONFIRMED",
                "physicalSensorBinding": "NOT_VERIFIED",
                "sharedRunProvenance": "NOT_VERIFIED",
                "measurementUnits": "NOT_VERIFIED",
            },
            "status": "PASS_PROVISIONAL" if mapping_matches and historian and historian["sampleCount"] > 0
                      else "REVIEW_REQUIRED",
        })
    return {
        "runId": run_id,
        "functions": results,
        "summary": {
            "functionCount": len(results),
            "provisionallySupported": sum(x["status"] == "PASS_PROVISIONAL" for x in results),
            "reviewRequired": sum(x["status"] == "REVIEW_REQUIRED" for x in results),
            "status": "PASS_PROVISIONAL" if results and all(x["status"] == "PASS_PROVISIONAL" for x in results)
                      else "REVIEW_REQUIRED",
            "physicalSensorBindingVerified": False,
            "sharedRunProvenanceVerified": False,
        },
    }


def audit(run_id, *, dsn, graphdb_url,
          mapping_discovery="reports/tep_nexus_mapping_discovery.json",
          temporal_coverage="reports/tep_nexus_temporal_coverage.json",
          registry_loader=load_supported_functions, post=requests.post,
          connect=psycopg.connect):
    run_id = str(UUID(str(run_id)))
    registry = registry_loader(mapping_discovery, temporal_coverage, run_id)
    response = post(graphdb_url, data={"query": SPARQL},
                    headers={"Accept": "application/sparql-results+json"}, timeout=30)
    response.raise_for_status()
    live = classify_bindings(response.json()["results"]["bindings"])
    signals = sorted({x["operational_signal"] for x in registry.values()})
    with connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(SQL, (run_id, signals))
                rows = cur.fetchall()
    counts = {
        signal: {"sampleCount": int(count), "minSimulationTimeHours": float(first),
                 "maxSimulationTimeHours": float(last)}
        for signal, count, first, last in rows
    }
    result = classify_evidence(registry, live, counts, run_id)
    return {
        "interface": "TEP NEXUS engineering mapping and provenance audit v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sources": {"semantic": "GraphDB AAS repository (path-constrained SPARQL)",
                    "temporal": "TimescaleDB public.signal_samples (read-only aggregate)"},
        "readOnly": True,
        "graphdbInvalidBindingCount": len(live["invalid_rows"]),
        **result,
        "limitations": [
            "GraphDB matching depends on AAS elementPath conventions and operational-reference equality.",
            "Source-query-confirmed matches do not establish independent physical sensor identity.",
            "Run ID is operator supplied; historian presence does not establish shared GraphDB/TimescaleDB run origin.",
            "GraphDB and TimescaleDB reads are not a distributed atomic snapshot.",
            "No fault causation, physical installation, or measurement-unit claim is made.",
            "This audit does not modify the planner allowlist or GraphDB repository.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--output", default="reports/tep_nexus_provenance_audit.json")
    args = parser.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")
    result = audit(args.run_id, dsn=dsn, graphdb_url=args.graphdb_url,
                   mapping_discovery=args.mapping_discovery,
                   temporal_coverage=args.temporal_coverage)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output), **result["summary"]}, indent=2))
    if result["summary"]["status"] != "PASS_PROVISIONAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
