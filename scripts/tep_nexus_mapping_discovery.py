"""Read-only discovery of candidate engineering-to-signal mappings in GraphDB.

Discovery is not approval: all returned mappings remain provisional until
independently reviewed. No changes to the planner allowlist are made.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

SPARQL = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX inv: <https://example.org/assetinventory/>
PREFIX aas: <https://example.org/aas/>
SELECT DISTINCT ?functionId ?functionRef ?signal ?asset WHERE {
  ?function dexpi:hasLocalId ?functionId ;
            dexpi:hasAssetIdentifier ?functionRef .
  ?mappingRef aas:value ?functionRef ;
              aas:elementPath ?refPath .
  ?signalNode aas:value ?signal ;
              aas:elementPath ?signalPath .
  BIND(STRBEFORE(STR(?refPath), ".EngineeringFunctionReference") AS ?mappingPath)
  FILTER(STR(?signalPath) = CONCAT(?mappingPath, ".SignalName"))
  ?asset inv:hasOperationalReference ?signal .
}
ORDER BY ?functionId ?signal ?asset
"""


def classify_bindings(bindings):
    """Conservatively classify GraphDB rows; duplicates are removed."""
    grouped = defaultdict(set)
    invalid = []
    for index, row in enumerate(bindings):
        try:
            values = tuple(row[key]["value"].strip() for key in
                           ("functionId", "functionRef", "signal", "asset"))
            if not all(values):
                raise ValueError("Empty mapping field")
            grouped[values[0]].add(values[1:])
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            invalid.append({"row_index": index, "reason": str(exc)})
    candidates = []
    for function_id, mappings in sorted(grouped.items()):
        entries = [
            {"function_reference": ref, "operational_signal": sig, "asset_uri": asset}
            for ref, sig, asset in sorted(mappings)
        ]
        candidates.append({
            "engineering_function": function_id,
            "mapping_count": len(entries),
            "status": "UNIQUE_PROVISIONAL_CANDIDATE" if len(entries) == 1
                      else "AMBIGUOUS_REVIEW_REQUIRED",
            "mappings": entries,
        })
    return {"candidates": candidates, "invalid_rows": invalid,
            "unique_candidate_count": sum(x["mapping_count"] == 1 for x in candidates),
            "ambiguous_function_count": sum(x["mapping_count"] > 1 for x in candidates)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--output", default="reports/tep_nexus_mapping_discovery.json")
    args = parser.parse_args()
    response = requests.post(
        args.graphdb_url, data={"query": SPARQL},
        headers={"Accept": "application/sparql-results+json"}, timeout=30,
    )
    response.raise_for_status()
    result = classify_bindings(response.json()["results"]["bindings"])
    report = {
        "interface": "TEP NEXUS GraphDB mapping discovery",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "GraphDB SPARQL",
        "mapping_confidence": "PROVISIONAL_NOT_PHYSICALLY_VERIFIED",
        "planner_allowlist_modified": False,
        **result,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Saved:", output)


if __name__ == "__main__":
    main()
