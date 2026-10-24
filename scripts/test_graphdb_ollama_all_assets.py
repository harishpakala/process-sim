#!/usr/bin/env python3
"""Verify all AssetInventory AAS assets against read-only live GraphDB results.

Uses the checked-in AAS JSON as the expected baseline. No Ollama call required.
"""
import argparse
import json
import os
from pathlib import Path
import sys

from ask_graphdb_ollama import ASSETS, PRODUCTS, direct_product_answer, graphdb_select

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "examples" / "aas" / "asset_inventory_instance.json"


def properties(collection):
    return {element["idShort"]: element.get("value") for element in collection.get("value", [])
            if element.get("modelType") == "Property"}


def expected_assets(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    groups = next(x for x in doc["submodelElements"] if x["idShort"] == "Assets")["value"]
    return {x["idShort"]: properties(x) for x in groups}


def validate(expected, assets, products, check_answers=True):
    errors = []
    seen = {}
    for asset in assets:
        label = asset.get("label")
        if not label:
            errors.append("GraphDB returned an asset without a label")
            continue
        if label in seen:
            errors.append(f"{label}: duplicate GraphDB asset row")
        seen[label] = asset
    product_by_id = {}
    for product in products:
        identifier = product.get("identifier")
        if not identifier:
            errors.append("GraphDB returned a product without AssetIdentifier")
        elif identifier in product_by_id:
            errors.append(f"Duplicate ProductCatalog identifier: {identifier}")
        else:
            product_by_id[identifier] = product

    for label in sorted(set(expected) - set(seen)):
        errors.append(f"{label}: missing from GraphDB")
    for label in sorted(set(seen) - set(expected)):
        errors.append(f"{label}: unexpected GraphDB asset")

    counts = {"product": 0, "candidate": 0, "unmapped": 0}
    for label, source in sorted(expected.items()):
        asset = seen.get(label)
        if asset is None:
            continue
        expected_ref = source.get("ProductReference") or None
        expected_candidate = source.get("CandidateProductReference") or None
        expected_status = source.get("CandidateSelectionStatus") or None
        actual_ref = asset.get("productRef") or None
        actual_candidate = asset.get("candidateRef") or None
        actual_status = asset.get("candidateStatus") or None
        if actual_ref != expected_ref:
            errors.append(f"{label}: ProductReference mismatch: expected {expected_ref!r}, got {actual_ref!r}")
        if actual_candidate != expected_candidate:
            errors.append(f"{label}: CandidateProductReference mismatch: expected {expected_candidate!r}, got {actual_candidate!r}")
        if actual_status != expected_status:
            errors.append(f"{label}: CandidateSelectionStatus mismatch: expected {expected_status!r}, got {actual_status!r}")

        if expected_ref:
            counts["product"] += 1
            product = product_by_id.get(actual_ref)
            if not product:
                errors.append(f"{label}: ProductReference has no matching ProductCatalog identifier")
        elif expected_candidate:
            counts["candidate"] += 1
            product = None
        else:
            counts["unmapped"] += 1
            product = None

        if check_answers:
            evidence = [{"asset": asset, "matched_product": product,
                         "source": "GraphDB AAS AssetInventory/ProductCatalog"}]
            answer = direct_product_answer(f"Which product is associated with {label}?", evidence)
            if not answer:
                errors.append(f"{label}: deterministic answer missing")
            elif label not in answer:
                errors.append(f"{label}: deterministic answer omits asset label")
            elif expected_ref and product and product.get("label") not in answer:
                errors.append(f"{label}: deterministic answer omits product label")
            elif expected_candidate and "provisional" not in answer.lower():
                errors.append(f"{label}: candidate answer does not say provisional")
            elif not expected_ref and not expected_candidate and "no ProductReference" not in answer:
                errors.append(f"{label}: unmapped answer does not report missing reference")
    return counts, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv("GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--evidence-only", action="store_true", help="Skip deterministic answer checks")
    args = parser.parse_args()
    try:
        expected = expected_assets(args.inventory)
        assets = graphdb_select(args.graphdb, ASSETS)
        products = graphdb_select(args.graphdb, PRODUCTS)
        counts, errors = validate(expected, assets, products, not args.evidence_only)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"Source assets: {len(expected)} | GraphDB asset rows: {len(assets)} | GraphDB product rows: {len(products)}")
    print(f"ProductReference: {counts['product']} | candidate-only: {counts['candidate']} | unmapped: {counts['unmapped']}")
    print(f"Mode: {'GraphDB evidence only' if args.evidence_only else 'GraphDB evidence + deterministic answers'}")
    for issue in errors:
        print(f"FAIL {issue}")
    print(f"Result: {'PASS' if not errors else 'FAIL'} ({len(errors)} issue(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
