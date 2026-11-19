"""Tests for compact evidence-grounded LLM-first relationship planning."""
import json
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_relation_selection import select_evidence_relation


class RelationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.anchors = [("A", "urn:A"), ("B", "urn:B")]
        self.catalog = {"entities": [
            {"domain": d, "shape": sh, "display_name": d,
             "properties": ["urn:hasAssetIdentifier"]}
            for d, sh in self.anchors]}
        self.mappings = [{
            "id": "verified1", "verified": True, "evidence_ids": ["ev1"],
            "left_domain": "A", "right_domain": "B",
            "left_property": "urn:hasAssetIdentifier",
            "right_property": "urn:hasAssetIdentifier"}]

    def run_choice(self, question, choice):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(choice)}}
        with patch("process_sim.dtwise.experimental_relation_selection.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan):
            result = select_evidence_relation(
                question, self.anchors, self.catalog, {}, self.mappings,
                model="mock", request_json=request,
                ollama_host="http://localhost", timeout=1)
        return result, calls

    def test_negative_paraphrase_selects_verified_anti_join(self):
        for question in (
            "Which A entities have no matching B by AssetIdentifier?",
            "Find A without a corresponding B.",
            "Return A records absent from B."):
            result, calls = self.run_choice(
                question, {"operation": "anti_join",
                           "mapping_id": "M0", "return_node": 0})
            plan, selection = result
            self.assertEqual(plan["anti_join"], {"from": "n0", "to": "n1"})
            self.assertEqual(plan["edges"][0]["mapping_id"], "verified1")
            self.assertEqual(selection["operation"], "anti_join")
            self.assertEqual(len(calls), 1)

    def test_positive_join_does_not_create_anti_join(self):
        result, _ = self.run_choice(
            "Find A matching B.", {"operation": "join",
                                    "mapping_id": "M0", "return_node": 0})
        self.assertNotIn("anti_join", result[0])

    def test_unknown_mapping_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown verified"):
            self.run_choice("Find A without B.", {
                "operation": "anti_join", "mapping_id": "M99",
                "return_node": 0})

    def test_unsupported_defers_to_full_llm_selector(self):
        result, _ = self.run_choice(
            "Count A matching B.", {"operation": "unsupported",
                                     "mapping_id": None, "return_node": 0})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
