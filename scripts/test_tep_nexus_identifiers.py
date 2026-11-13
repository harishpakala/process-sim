#!/usr/bin/env python3
"""Regression checks for the TEP NEXUS asset/product identifier convention."""

# Created: 2026-11-02
# Author: Harish
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "examples" / "aas"

def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def field(record, name):
    return next((p.get("value") for p in record.get("value", []) if p.get("idShort") == name), None)

def test_identifiers_and_product_links():
    assets = next(x["value"] for x in load("asset_inventory_instance.json")["submodelElements"] if x["idShort"] == "Assets")
    products = next(x["value"] for x in load("product_catalog_instance.json")["submodelElements"] if x["idShort"] == "Products")
    asset_ids = [field(x, "AssetIdentifier") for x in assets]
    product_ids = [field(x, "ProductIdentifier") for x in products]
    assert all(asset_ids) and len(set(asset_ids)) == len(asset_ids)
    assert all(product_ids) and len(set(product_ids)) == len(product_ids)
    assert all(field(x, "AssetId") is None for x in assets)
    assert all(field(x, "AssetIdentifier") is None for x in products)
    links = [field(x, "ProductIdentifier") for x in assets if field(x, "ProductIdentifier")]
    assert links and all(x in set(product_ids) for x in links)
    for name, old, new in [
        ("asset_inventory_template.json", "AssetId", "AssetIdentifier"),
        ("product_catalog_template.json", "AssetIdentifier", "ProductIdentifier"),
    ]:
        text = json.dumps(load(name))
        assert '"idShort": "' + new + '"' in text
        assert '"idShort": "' + old + '"' not in text
    ebom = next(x["value"] for x in load("tep_engineering_bom_instance.json")["submodelElements"] if x["idShort"] == "BOMItems")
    ebom_items = {
        field(x, "BOMItemId"): x for x in ebom
    }
    product_set = set(product_ids)
    asset_set = set(asset_ids)
    for item in ebom:
        names = [p["idShort"] for p in item["value"] if p.get("modelType") == "Property"]
        assert len(names) == len(set(names)), field(item, "BOMItemId")
        assert "AssetIdentifier" in names and "ProductIdentifier" in names
        assert "AssetReference" not in names and "CandidateProductReference" not in names
        assert not field(item, "ProductIdentifier") or field(item, "ProductIdentifier") in product_set
        assert field(item, "ValidationStatus") == (
            "ASSET_IDENTIFIER_EXACT_MATCH" if field(item, "AssetIdentifier") in asset_set
            else "ASSET_INVENTORY_MATCH_UNRESOLVED"
        )
    for identifier in ("EBOM-0016", "EBOM-0050"):
        item = ebom_items[identifier]
        assert field(item, "AssetIdentifier") == "https://aas.example.com/TI101"
        assert field(item, "ProductIdentifier") == "https://example.org/product-types/IFM_TA1101"
        assert field(item, "StructureStatus") == "UNASSIGNED_NO_VERIFIED_EQUIPMENT_MEMBERSHIP"
    assert len(ebom_items) == len(ebom) == 79
    assert sum(bool(field(x, "ProductIdentifier")) for x in ebom) == 63
    print(f"PASS: {len(assets)} distinct asset identifiers, {len(products)} distinct product identifiers, {len(links)} resolved product links")

if __name__ == "__main__":
    test_identifiers_and_product_links()
