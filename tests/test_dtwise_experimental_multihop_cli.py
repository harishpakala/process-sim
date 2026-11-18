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
        with self.assertRaisesRegex(ValueError, "requires a named SHACL shape"):
            self.plan("Find connected assets")

    def test_unverified_mapping_rejected_before_llm(self):
        with self.assertRaisesRegex(ValueError, "No verified evidence path"):
            self.plan("Find Plant Signal", mappings=[
                dict(self.mappings[0], verified=False)])

    def test_named_intermediate_is_required_waypoint(self):
        # Plant -> Instrument -> Signal is the only evidenced two-hop path.
        # The explicitly named Instrument must appear in the candidate.
        seen = []

        def fake_request(url, payload, timeout):
            seen.append(payload)
            return {"message": {"content": '{"path_id":null,"operation":"unsupported","projections":[],"filter":null}'}}

        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=self.catalog), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                side_effect=lambda catalog, question: (
                    catalog, {"dexpi", "opc"})):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                plan_experimental_multihop(
                    "Get Signal from Plant through Instrument", {},
                    self.mappings, model="test",
                    ollama_host="http://localhost:11434",
                    timeout=1, request_json=fake_request)
        self.assertEqual(len(seen), 1)
        self.assertIn('"shape":"Instrument"',
                      seen[0]["messages"][1]["content"])

    def test_unreachable_named_waypoint_rejected(self):
        # All three shapes are named but one relationship is absent.
        self.catalog["shacl_edges"] = []
        with self.assertRaisesRegex(ValueError, "includes all named"):
            self.plan("Find Plant Instrument Signal")


    def test_verified_one_edge_path_is_offered_to_llm(self):
        seen = []
        def fake_request(url, payload, timeout):
            seen.append(payload)
            return {"message": {"content": '{"path_id":null,"operation":"unsupported","projections":[],"filter":null}'}}
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=self.catalog), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                side_effect=lambda catalog, question: (
                    catalog, {"dexpi", "opc"})):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                plan_experimental_multihop(
                    "Find Instrument Signal", {}, self.mappings,
                    model="test", ollama_host="http://localhost:11434",
                    timeout=1, request_json=fake_request)
        self.assertEqual(len(seen), 1)
        self.assertIn("asset", seen[0]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
