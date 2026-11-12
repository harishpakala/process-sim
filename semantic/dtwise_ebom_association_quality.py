"""Classify EngineeringBOM association evidence without claiming asset identity.

Usage:
  python -m semantic.dtwise_ebom_association_quality graphdb-ebom-results.json

Consumes SPARQL Results JSON with assetIdentifier, bomRecord, bomItemId,
revision, engineeringLocalId and associationBasis. Unknown/missing evidence is
reported explicitly, never treated as confirmation or silently filtered.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

FUNCTIONAL = "SOURCE_NAME_OR_DESCRIPTION_FUNCTIONAL_ASSOCIATION_NOT_PHYSICAL_MEMBERSHIP"
UNRESOLVED = "UNRESOLVED"
FIELDS = ("assetIdentifier", "bomRecord", "bomItemId", "revision",
          "engineeringLocalId", "associationBasis")


def assess(document):
    rows = document["results"]["bindings"]
    grouped = defaultdict(list)
    statuses = Counter()
    revisions = Counter()
    missing_fields = Counter()
    records = set()
    bom_ids = set()
    local_ids = set()
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"row {number}: expected binding object")
        values = {}
        for key in FIELDS:
            binding = row.get(key)
            value = binding.get("value") if isinstance(binding, dict) else None
            if value is None or value == "":
                missing_fields[key] += 1
                value = None
            values[key] = value
        if not values["assetIdentifier"] or not values["bomRecord"]:
            raise ValueError(f"row {number}: assetIdentifier and bomRecord are required")
        grouped[values["assetIdentifier"]].append(values)
        records.add(values["bomRecord"])
        if values["bomItemId"]:
            bom_ids.add(values["bomItemId"])
        if values["engineeringLocalId"]:
            local_ids.add(values["engineeringLocalId"])
        statuses[values["associationBasis"] or "MISSING"] += 1
        revisions[values["revision"] or "MISSING"] += 1

    pair_types = Counter()
    for identifier, members in grouped.items():
        kinds = {m["associationBasis"] or "MISSING" for m in members}
        if len(members) != 2:
            pair_types["other_multiplicity"] += 1
        elif kinds == {FUNCTIONAL}:
            pair_types["both_functional_not_physical"] += 1
        elif kinds == {UNRESOLVED}:
            pair_types["both_unresolved"] += 1
        elif kinds == {FUNCTIONAL, UNRESOLVED}:
            pair_types["mixed_functional_unresolved"] += 1
        else:
            pair_types["other_or_unknown"] += 1

    return {
        "classification": "identifier_associations_only_not_semantically_confirmed",
        "semantically_confirmed_asset_relationships": 0,
        "semantic_confirmation_assessed": False,
        "counts": {
            "rows": len(rows),
            "shared_identifiers": len(grouped),
            "distinct_bom_records": len(records),
            "distinct_bom_item_ids": len(bom_ids),
            "distinct_engineering_local_ids": len(local_ids),
        },
        "association_basis": dict(sorted(statuses.items())),
        "revision": dict(sorted(revisions.items())),
        "identifier_groups": dict(sorted(pair_types.items())),
        "missing_fields": dict(sorted(missing_fields.items())),
        "warnings": [
            "Identifier equality does not establish physical asset membership.",
            "Functional association explicitly does not establish physical membership.",
            "UNRESOLVED evidence must not be interpreted as semantic approval.",
            "UNSPECIFIED revision cannot establish revision-based duplication.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", type=Path)
    args = parser.parse_args()
    try:
        result = assess(json.loads(args.results_json.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"association-quality assessment failed: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
