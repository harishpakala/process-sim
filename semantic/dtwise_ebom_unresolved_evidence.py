"""Read-only GraphDB evidence export for unresolved EngineeringBOM associations.

Usage:
  python -m semantic.dtwise_ebom_unresolved_evidence --endpoint http://localhost:7200/repositories/AAS --output unresolved-ebom-evidence.json

Collects all direct RDF predicates/values on BOM records with unresolved
association basis, preserving provenance without interpreting asset identity.
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from semantic.dtwise_graphdb_integration import execute

QUERY = """PREFIX ebom: <https://example.org/engineeringbom/>
SELECT DISTINCT ?assetIdentifier ?bomRecord ?predicate ?value
WHERE {
  ?root ebom:hasBOMItems/ebom:hasBOMItemRecord ?bomRecord .
  ?bomRecord ebom:hasAssetIdentifier ?assetIdentifier ;
             ebom:hasAssociationBasis "UNRESOLVED" ;
             ?predicate ?value .
}
ORDER BY ?assetIdentifier ?bomRecord ?predicate ?value
LIMIT 10000
"""


def summarize(document):
    groups = defaultdict(lambda: {"asset_identifier": None, "record_uri": None,
                                  "properties": defaultdict(list)})
    for number, binding in enumerate(document["results"]["bindings"], 1):
        try:
            identifier = binding["assetIdentifier"]["value"]
            record = binding["bomRecord"]["value"]
            predicate = binding["predicate"]["value"]
            value = binding["value"]
            if not all((identifier, record, predicate)) or not isinstance(value, dict):
                raise ValueError("empty required field")
            if "value" not in value or "type" not in value:
                raise ValueError("invalid RDF value binding")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {number}: invalid SPARQL binding: {exc}") from exc
        item = groups[record]
        if item["asset_identifier"] not in (None, identifier):
            raise ValueError(f"row {number}: conflicting identifiers for {record}")
        item["asset_identifier"] = identifier
        item["record_uri"] = record
        evidence = {key: value[key] for key in ("type", "value", "datatype", "xml:lang")
                    if key in value}
        if evidence not in item["properties"][predicate]:
            item["properties"][predicate].append(evidence)
    records = []
    for record in sorted(groups):
        item = groups[record]
        item["properties"] = {key: sorted(vals, key=lambda v: json.dumps(v, sort_keys=True))
                              for key, vals in sorted(item["properties"].items())}
        records.append(item)
    return {
        "classification": "unresolved_associations_for_domain_owner_review",
        "semantic_approval": "not_granted",
        "counts": {"unresolved_records": len(records),
                   "asset_identifiers": len({x["asset_identifier"] for x in records})},
        "records": records,
        "warnings": [
            "Direct RDF properties are evidence, not confirmation of physical membership.",
            "Missing provenance or source descriptions must remain unresolved.",
            "The query limit is 10000 rows; check truncation before relying on completeness.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        document = execute(args.endpoint, QUERY, timeout=args.timeout,
                           username=os.environ.get("GRAPHDB_USER"),
                           password=os.environ.get("GRAPHDB_PASSWORD"))
        if len(document["results"]["bindings"]) >= 10000:
            raise ValueError("Query reached LIMIT 10000; evidence may be truncated")
        report = summarize(document)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Unresolved evidence export failed: {exc}\n")
    print(json.dumps({"output": str(args.output), "counts": report["counts"],
                      "semantic_approval": report["semantic_approval"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
