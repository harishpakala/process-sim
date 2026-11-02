#!/usr/bin/env python3
"""Regression checks for the TEP NEXUS asset/product identifier convention."""
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
    print(f"PASS: {len(assets)} distinct asset identifiers, {len(products)} distinct product identifiers, {len(links)} resolved product links")

if __name__ == "__main__":
    test_identifiers_and_product_links()
