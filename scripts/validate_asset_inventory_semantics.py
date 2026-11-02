#!/usr/bin/env python3
"""Check AssetInventory semantic IDs and provisional ProductCatalog links.

Run: python scripts/validate_asset_inventory_semantics.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "examples/aas/asset_inventory_instance.json"
CATALOG_PATH = ROOT / "examples/aas/product_catalog_instance.json"
LOCAL_PREFIX = "https://example.org/tep/ontology/asset-inventory#"
LOGICAL_TYPES = {
    "LogicalMeasurement", "LogicalManipulatedVariable", "LogicalMotorControl",
    "IllustrativeMotor", "IllustrativeControlValve",
}

def prop(record, name):
    return next((v.get("value") for v in record.get("value", []) if v.get("idShort") == name), None)

def semantic(record):
    keys = record.get("semanticId", {}).get("keys", [])
    assert len(keys) == 1 and keys[0].get("type") == "GlobalReference", record.get("idShort")
    assert record["semanticId"].get("type") == "ExternalReference"
    return keys[0]["value"]

def main():
    inventory = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assets = next(e["value"] for e in inventory["submodelElements"] if e["idShort"] == "Assets")
    products = next(e["value"] for e in catalog["submodelElements"] if e["idShort"] == "Products")
    by_identifier = {prop(p, "ProductIdentifier"): p for p in products}
    assert len(by_identifier) == len(products)
    assert len({a["idShort"] for a in assets}) == len(assets)
    assert len({prop(a, "AssetIdentifier") for a in assets}) == len(assets)
    candidate_count = 0
    for asset in assets:
        asset_type = prop(asset, "AssetType")
        classification = semantic(asset)
        assert prop(asset, "AssetIdentifier") and prop(asset, "EquipmentTag")
        assert not prop(asset, "InstalledProductReference"), asset["idShort"]
        candidate = prop(asset, "CandidateProductReference")
        if asset_type in LOGICAL_TYPES:
            assert classification == LOCAL_PREFIX + asset_type, asset["idShort"]
            assert not candidate, asset["idShort"]
        elif asset_type == "SimulatedEquipment":
            assert candidate in by_identifier, asset["idShort"]
            product = by_identifier[candidate]
            assert classification == semantic(product), asset["idShort"]
            assert classification == prop(product, "ECLASSIRDI"), asset["idShort"]
            assert prop(asset, "CandidateSelectionStatus") == prop(product, "SelectionStatus")
            assert prop(asset, "CandidateSelectionStatus") in {
                "PROVISIONAL_CANDIDATE", "REQUIRES_ALTERNATIVE"
            }
            candidate_count += 1
        else:
            raise AssertionError(f"Unrecognized asset type: {asset_type}")
    assert len(assets) == 62, len(assets)
    assert candidate_count == 5, candidate_count
    print(f"PASS: {len(assets)} assets have semanticIds; {candidate_count} provisional catalog references consistent")

if __name__ == "__main__":
    main()
