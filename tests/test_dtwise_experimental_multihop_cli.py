"""Fail-closed offline tests for opt-in multi-hop CLI orchestration."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import plan_experimental_multihop


class ExperimentalMultihopCliTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "entities": [
                {"domain": "dexpi", "shape": "urn:Plant",
                 "display_name": "Plant", "properties": ["urn:hasInstrument"]},
                {"domain": "dexpi", "shape": "urn:Instrument",
                 "display_name": "Instrument", "properties": ["urn:asset"]},
                {"domain": "opc", "shape": "urn:Signal",
                 "display_name": "Signal", "properties": ["urn:opcAsset"]},
            ],
            "shacl_edges": [
                {"domain": "dexpi", "from_shape": "urn:Plant",
                 "to_shape": "urn:Instrument",
                 "predicate": "urn:hasInstrument"}],
        }
        self.mappings = [{
            "id": "asset", "verified": True, "evidence_ids": ["e1"],
            "left_domain": "dexpi", "right_domain": "opc",
            "left_property": "urn:asset", "right_property": "urn:opcAsset",
        }]

    def plan(self, question, mappings=None):
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=self.catalog), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                side_effect=lambda catalog, question: (
                    catalog, {"dexpi", "opc"})):
            return plan_experimental_multihop(
                question, {}, self.mappings if mappings is None else mappings,
                model="test", ollama_host="http://localhost:11434",
                timeout=1, request_json=lambda *args: self.fail(
                    "No LLM call expected"))

    def test_unnamed_endpoints_rejected_before_llm(self):
        with self.assertRaisesRegex(ValueError, "exactly two"):
            self.plan("Find connected assets")

    def test_unverified_mapping_rejected_before_llm(self):
        with self.assertRaisesRegex(ValueError, "No verified multi-hop"):
            self.plan("Find Plant Signal", mappings=[
                dict(self.mappings[0], verified=False)])

    def test_no_multihop_path_rejected_before_llm(self):
        with self.assertRaisesRegex(ValueError, "No verified multi-hop"):
            self.plan("Find Instrument Signal")


if __name__ == "__main__":
    unittest.main()
