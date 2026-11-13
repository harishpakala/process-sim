"""Validate an exported GraphDB four-domain SELECT result against observed counts.

Usage: python -m semantic.dtwise_four_domain_baseline "graphdb-results.json"
No GraphDB credentials or network connection are required.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

BASELINE = Path(__file__).resolve().parent / "ontology" / "dtwise" / "four-domain-graphdb-baseline.json"


def validate_result(document, baseline):
    expected = baseline["expected"]
    entity_keys = baseline["columns"]["entities"]
    id_keys = baseline["columns"]["identifiers"]
    rows = document["results"]["bindings"]
    failures = []
    if len(rows) != expected["rows"]:
        failures.append(f"rows: expected {expected['rows']}, got {len(rows)}")
    entities = {key: set() for key in entity_keys}
    identifiers = set()
    multiplicities = Counter()
    distinct_tuples = set()
    for row_number, row in enumerate(rows, 1):
        try:
            values = [row[key]["value"] for key in entity_keys + id_keys]
        except (KeyError, TypeError) as exc:
            failures.append(f"row {row_number}: missing or invalid binding {exc}")
            continue
        entity_values = values[:len(entity_keys)]
        id_values = values[len(entity_keys):]
        if len(set(id_values)) != 1:
            failures.append(f"row {row_number}: cross-domain identifiers differ")
        identifier = id_values[0]
        identifiers.add(identifier)
        multiplicities[identifier] += 1
        for key, value in zip(entity_keys, entity_values):
            entities[key].add(value)
        tuple_key = tuple(values)
        if tuple_key in distinct_tuples:
            failures.append(f"row {row_number}: duplicate projected result")
        distinct_tuples.add(tuple_key)
    actual = {
        "rows": len(rows),
        "shared_identifiers": len(identifiers),
        "engineeringbom_records": len(entities["entity0"]),
        "ecad_devices": len(entities["entity1"]),
        "dexpi_objects": len(entities["entity2"]),
        "assetinventory_assets": len(entities["entity3"]),
    }
    for key, observed in actual.items():
        if key in expected and observed != expected[key]:
            failures.append(f"{key}: expected {expected[key]}, got {observed}")
    target = expected.get("bom_records_per_identifier")
    if target is not None:
        unexpected = {key: value for key, value in multiplicities.items() if value != target}
        if unexpected:
            failures.append(f"identifier row multiplicity differs from {target}: {unexpected}")
    return actual, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", type=Path, help="GraphDB SPARQL JSON results export")
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    document = json.loads(args.results_json.read_text(encoding="utf-8"))
    actual, failures = validate_result(document, baseline)
    print(json.dumps({"counts": actual, "passed": not failures, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
