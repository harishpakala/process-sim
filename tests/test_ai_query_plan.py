"""Tests for SHACL-grounded structured query plans, with no live services."""

# Created: 2026-10-23
# Author: Harish
import unittest

from process_sim.ai.query_plan import validate_plan


def registry():
    return {"domains": [{"domain": "dexpi", "shaclPaths": [
        {"parentPredicate": None, "predicate": "https://example.org/dexpi/hasEquipments"},
        {"parentPredicate": "https://example.org/dexpi/hasEquipments",
         "predicate": "https://example.org/dexpi/hasEquipment"},
        {"parentPredicate": "https://example.org/dexpi/hasEquipment",
         "predicate": "https://example.org/dexpi/hasAssetIdentifier"},
    ]}]}


class StructuredQueryTests(unittest.TestCase):
    def test_valid_template_path(self):
        result = validate_plan({"domain": "dexpi", "path": [
            "https://example.org/dexpi/hasEquipments",
            "https://example.org/dexpi/hasEquipment",
            "https://example.org/dexpi/hasAssetIdentifier"], "limit": 20}, registry())
        self.assertIn("SELECT DISTINCT", result.sparql)
        self.assertIn("LIMIT 20", result.sparql)

    def test_rejects_invented_relationship(self):
        with self.assertRaises(ValueError):
            validate_plan({"domain": "dexpi", "path": [
                "https://example.org/dexpi/hasImaginary"], "limit": 20}, registry())

    def test_rejects_wrong_parent_chain(self):
        with self.assertRaises(ValueError):
            validate_plan({"domain": "dexpi", "path": [
                "https://example.org/dexpi/hasEquipments",
                "https://example.org/dexpi/hasAssetIdentifier"], "limit": 20}, registry())

    def test_rejects_bad_limit_and_extra_fields(self):
        for limit in (0, 201, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                validate_plan({"domain": "dexpi", "path": [
                    "https://example.org/dexpi/hasEquipments"], "limit": limit}, registry())
        with self.assertRaises(ValueError):
            validate_plan({"domain": "dexpi", "path": [
                "https://example.org/dexpi/hasEquipments"], "limit": 10,
                "sparql": "DROP ALL"}, registry())

    def test_rejects_other_domain(self):
        with self.assertRaises(ValueError):
            validate_plan({"domain": "ecad", "path": [
                "https://example.org/dexpi/hasEquipments"], "limit": 10}, registry())


if __name__ == "__main__":
    unittest.main()
