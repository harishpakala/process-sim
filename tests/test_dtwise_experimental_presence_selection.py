"""Regression tests for LLM-first property presence/absence semantics."""
import json
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_presence_selection import select_presence_plan


class PresenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.anchor = ("AssetInventory", "urn:Asset")
        self.catalog = {"entities": [{
            "domain": "AssetInventory", "shape": "urn:Asset",
            "display_name": "Asset",
            "properties": ["https://example.org/hasAssetName",
                           "https://example.org/hasEquipmentTag"]}]}

    def select(self, question, choice):
        requests = []
        def request(url, payload, timeout):
            requests.append(payload)
            return {"message": {"content": json.dumps(choice)}}
        with patch("process_sim.dtwise.experimental_presence_selection.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan):
            result = select_presence_plan(
                question, self.anchor, self.catalog, {}, [],
                model="mock", request_json=request,
                ollama_host="http://localhost", timeout=1)
        return result, requests

    def test_positive_and_negative_properties(self):
        result, calls = self.select(
            "Which AssetInventory Asset entities have AssetName but no EquipmentTag?",
            {"operation": "presence", "present_ids": ["P0"],
             "absent_ids": ["P1"]})
        plan, _ = result
        self.assertTrue(plan["return_entities"])
        self.assertEqual(plan["projections"], [])
        self.assertEqual(plan["filters"]["op"], "and")
        self.assertEqual([f["op"] for f in plan["filters"]["children"]],
                         ["exists", "not_exists"])
        self.assertEqual(len(calls), 1)

    def test_coverage_treats_presence_as_filters_not_projections(self):
        from process_sim.dtwise.unified_answer import check_semantic_coverage
        result, _ = self.select(
            "Which AssetInventory Asset entities have AssetName but no EquipmentTag?",
            {"operation": "presence", "present_ids": ["P0"],
             "absent_ids": ["P1"]})
        plan, _ = result
        check_semantic_coverage(plan,
            "Which AssetInventory Asset entities have AssetName but no EquipmentTag?",
            self.catalog, {"assetinventory"})

    def test_coverage_rejects_missing_presence_predicate(self):
        from process_sim.dtwise.unified_answer import check_semantic_coverage
        result, _ = self.select(
            "Which AssetInventory Asset entities have AssetName but no EquipmentTag?",
            {"operation": "presence", "present_ids": ["P0"],
             "absent_ids": ["P1"]})
        plan, _ = result
        plan["filters"]["children"][0]["predicate"] = "https://example.org/hasOther"
        with self.assertRaisesRegex(ValueError, "projection omitted"):
            check_semantic_coverage(plan,
                "Which AssetInventory Asset entities have AssetName but no EquipmentTag?",
                self.catalog, {"assetinventory"})

    def test_invented_property_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invented"):
            self.select("Asset without EquipmentTag but with AssetName", {
                "operation": "presence", "present_ids": ["P0"],
                "absent_ids": ["P99"]})

    def test_ordinary_substring_query_does_not_trigger(self):
        result, calls = self.select(
            "Asset with AssetName containing reactor",
            {"operation": "presence", "present_ids": ["P0"],
             "absent_ids": ["P1"]})
        self.assertIsNone(result)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
