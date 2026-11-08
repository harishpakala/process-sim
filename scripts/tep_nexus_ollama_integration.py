"""Created: 2026-11-01
Author: Harish"""

import os
import sys
import json
import urllib.request
import urllib.parse

import psycopg

QUERY = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX inv: <https://example.org/assetinventory/>
PREFIX aas: <https://example.org/aas/>

SELECT DISTINCT ?functionRef ?signal ?asset
WHERE {
  ?function dexpi:hasLocalId "TI_101" ;
            dexpi:hasAssetIdentifier ?functionRef .
  ?mappingRef aas:value ?functionRef ;
              aas:elementPath ?refPath .
  ?signalNode aas:value ?signal ;
              aas:elementPath ?signalPath .
  BIND(STRBEFORE(STR(?refPath), ".EngineeringFunctionReference") AS ?mappingPath)
  FILTER(STR(?signalPath) = CONCAT(?mappingPath, ".SignalName"))
  ?asset inv:hasOperationalReference ?signal .
}
LIMIT 20
"""

def main():
    endpoint = os.getenv(
        "GRAPHDB_SPARQL_URL",
        "http://localhost:7200/repositories/AAS"
    )

    request = urllib.request.Request(
        endpoint,
        data=urllib.parse.urlencode({"query": QUERY}).encode(),
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)

    mappings = [
        {key: value["value"] for key, value in row.items()}
        for row in data["results"]["bindings"]
    ]

    signals = sorted({row["signal"] for row in mappings})

    if len(signals) != 1:
        print(json.dumps({
            "status": "NO_UNAMBIGUOUS_MAPPING",
            "mappings": mappings
        }, indent=2))
        return

    signal = signals[0]

    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        sys.exit("TEP_TIMESCALE_DSN is not configured.")

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")

            cur.execute("""
                SELECT run_id, COUNT(*),
                       MIN(simulation_time_hours),
                       MAX(simulation_time_hours)
                FROM public.signal_samples
                WHERE signal_id = %s
                GROUP BY run_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """, (signal,))

            summary = cur.fetchone()

            if not summary:
                sys.exit("No temporal samples found for " + signal)

            run_id, count, first, last = summary

            cur.execute("""
                SELECT simulation_time_hours, value
                FROM public.signal_samples
                WHERE run_id = %s AND signal_id = %s
                ORDER BY simulation_time_hours ASC
                LIMIT 5
            """, (run_id, signal))

            samples = cur.fetchall()

    evidence = {
        "engineering_function": "TI_101",
        "mapping_status": "PROVISIONAL_ENGINEERING_MATCH",
        "graphdb_mapping": mappings,
        "signal": signal,
        "run_id": str(run_id),
        "sample_count": count,
        "first_time_hours": first,
        "last_time_hours": last,
        "first_five_samples": [
            {"time_hours": t, "value": v}
            for t, v in samples
        ]
    }

    if "--evidence-only" in sys.argv:
        print(json.dumps({
            "status": "EVIDENCE_ONLY",
            "evidence": evidence
        }, indent=2))
        return

    question = (
        "Show reactor temperature measurements for TI_101 "
        "and explain the mapped signal."
    )

    payload = json.dumps({
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer using only the supplied evidence. "
                    "State the engineering function, signal, run ID, "
                    "sample count and simulation time range. "
                    "The engineering mapping is provisional. "
                    "Do not claim physical installation or live OPC UA "
                    "connectivity. The initial zero measurement may "
                    "be initialization. Do not infer fault causation."
                )
            },
            {
                "role": "user",
                "content": question + "\nEvidence:\n"
                           + json.dumps(evidence)
            }
        ]
    }).encode()

    ollama_url = os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434"
    ).rstrip("/") + "/api/chat"

    request = urllib.request.Request(
        ollama_url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)


    answer = result["message"]["content"]

    checks = {
        "engineering_function_present": "TI_101" in answer,
        "signal_present": "XMEAS9" in answer,
        "run_id_present": str(run_id) in answer,
        "sample_count_present": str(count) in answer,
        "provisional_mapping_disclosed": (
            "provisional" in answer.lower()
        ),
        "initial_zero_caveat_present": (
            "initialization" in answer.lower()
            or "initial zero" in answer.lower()
            or "initial reading" in answer.lower()
        )
    }

    all_passed = all(checks.values())

    print(json.dumps({
        "status": (
            "VALIDATION_PASS" if all_passed
            else "VALIDATION_REVIEW_REQUIRED"
        ),
        "answer": answer,
        "validation": checks,
        "evidence": evidence
    }, indent=2))


if __name__ == "__main__":
    main()
