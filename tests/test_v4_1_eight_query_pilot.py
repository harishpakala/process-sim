"""Offline regression tests for the V4.1 pilot safety boundary."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from ontology_nl2sparql_generic_v4_1 import joins, minimum_joins, validate
from run_v4_1_eight_query_pilot import preflight
from q13_extract_focused_schema import extract


class PilotTests(unittest.TestCase):
    def test_hypothesis_joins_disabled_by_default(self):
        cat = {
            "s0": {"domain": "dexpi", "properties": [{"predicate": "urn:a#hasAssetIdentifier"}]},
            "s1": {"domain": "ecad", "properties": [{"predicate": "urn:b#hasAssetIdentifier"}]},
        }
        self.assertEqual(joins(cat), {})
        self.assertEqual(len(joins(cat, allow_hypothesis_joins=True)), 1)
        plan = {"fields": [
            {"name": "a", "shape": "s0", "predicate": "urn:a#hasAssetIdentifier"},
            {"name": "b", "shape": "s1", "predicate": "urn:b#hasAssetIdentifier"},
        ], "filters": [], "unsupported": []}
        with self.assertRaises(ValueError):
            minimum_joins(plan, cat, joins(cat), ["dexpi", "ecad"])

    def test_nonexistent_predicate_rejected(self):
        cat = {"s0": {"domain": "ecad", "properties": [
            {"predicate": "urn:x#hasLocalId", "kind": "datatype"}]}}
        plan = {"fields": [{"name": "fake", "shape": "s0",
                             "predicate": "urn:x#nonexistent"}],
                "filters": [], "unsupported": []}
        self.assertIn("Undeclared field property", validate(plan, cat, [], [], "List fake"))

    def test_eight_cases_exist_in_shacl(self):
        import json
        manifest = json.loads((ROOT / "experiments/benchmarks/v4_1_eight_query_pilot.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["cases"]), 8)
        schema = extract()
        for case in manifest["cases"]:
            with self.subTest(case=case["id"]):
                self.assertIsNone(preflight(case, schema))


if __name__ == "__main__":
    unittest.main()
