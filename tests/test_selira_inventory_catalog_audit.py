"""Inventory/catalog integrity and simulation-only analyzer policy tests."""
import json
from pathlib import Path

from process_sim.selira.inventory_catalog_audit import audit_inventory_catalog


ROOT = Path(__file__).resolve().parents[1] / "examples" / "aas"


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_inventory_catalog_links_and_explicit_analyzer_review():
    results = audit_inventory_catalog(
        _load("asset_inventory_instance.json"),
        _load("product_catalog_instance.json"),
    )
    assert len(results) == 62
    assert sum(x.status == "linked_unverified" for x in results) == 43
    assert sum(x.status == "unassigned_review" for x in results) == 19
    assert not any(x.status in ("broken_reference", "missing_assignment",
                                "ambiguous_product", "conflicting_references")
                   for x in results)
    assert {x.asset for x in results if x.status == "unassigned_review"} == {
        f"TEP_XMEAS{i}" for i in range(23, 42)
    }


def test_pressure_inventory_tag_and_catalog_reference():
    inventory = _load("asset_inventory_instance.json")
    assets = inventory["submodelElements"][0]["value"]
    pressure = next(x for x in assets if x["idShort"] == "TEP_XMEAS7")
    props = {x["idShort"]: x["value"] for x in pressure["value"]
             if x["modelType"] == "Property"}
    assert props["EquipmentTag"] == "PI-1101"
    assert props["ProductReference"].endswith("/EandH_PMP51B_Candidate")
