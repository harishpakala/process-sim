"""Source-level ProductCatalog/AssetInventory regression checks (stdlib only).

Run: python3 -m unittest discover -s tests -p 'test_aas_catalog_inventory_contract.py'
These checks do not replace AAS metamodel, RDF or SHACL validation.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "examples/aas/product_catalog_instance.json"
INVENTORY = ROOT / "examples/aas/asset_inventory_instance.json"
REQUIRED_ECLASS = ("ECLASSClass", "ECLASSPreferredName", "ECLASSIRDI")
RETIRED = {"Unspecified_MotorDrive_Reference", "Unspecified_AgitatorDrive_Reference"}


def records(path, collection):
    submodel = json.loads(path.read_text(encoding="utf-8"))
    assert submodel["modelType"] == "Submodel"
    container = next(x for x in submodel["submodelElements"] if x["idShort"] == collection)
    return container["value"]


def properties(record):
    return {item["idShort"]: item.get("value") for item in record["value"]
            if item["modelType"] == "Property"}


class CatalogInventoryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = records(CATALOG, "Products")
        cls.assets = records(INVENTORY, "Assets")

    def test_catalog_ids_unique(self):
        ids = [x["idShort"] for x in self.products]
        self.assertEqual(len(ids), len(set(ids)))

    def test_catalog_identifiers_unique(self):
        ids = [properties(x).get("ProductIdentifier") for x in self.products]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_eclass_fields_populated(self):
        for record in self.products:
            with self.subTest(product=record["idShort"]):
                props = properties(record)
                for field in REQUIRED_ECLASS:
                    self.assertTrue(props.get(field), f"{record['idShort']}: missing {field}")

    def test_no_retired_placeholders(self):
        self.assertFalse(RETIRED.intersection(x["idShort"] for x in self.products))

    def test_inventory_references_resolve(self):
        known = {properties(x)["ProductIdentifier"] for x in self.products}
        for asset in self.assets:
            ref = properties(asset).get("ProductIdentifier")
            if ref:
                with self.subTest(asset=asset["idShort"]):
                    self.assertIn(ref, known)

    def test_inventory_asset_ids_unique(self):
        ids = [properties(x).get("AssetIdentifier") for x in self.assets]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_inventory_asset_names_unique(self):
        ids = [x["idShort"] for x in self.assets]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
