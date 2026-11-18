"""Offline B01-B05 compatibility checks for experimental zero-edge planning."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import plan_experimental_multihop


CASES = [
    ("opcuaconnectivity", "SignalMapping", "SignalName"),
    ("dexpi", "InstrumentationFunction", "LocalId"),
    ("dexpi", "InstrumentationFunction", "MeasuredVariable"),
    ("assetinventory", "Asset", "AssetName"),
    ("productcatalog", "Product", "ManufacturerName"),
]


class ExperimentalSingleShapeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [], "shacl_edges": []}
        for domain, label, prop in CASES:
            entity = next((e for e in self.catalog["entities"]
                           if e["domain"] == domain and
                           e["display_name"] == label), None)
            if entity is None:
                entity = {"domain": domain, "shape": "urn:" + domain + ":" + label,
                          "display_name": label, "properties": []}
                self.catalog["entities"].append(entity)
            entity["properties"].append(
                "https://example.org/" + domain + "/has" + prop)

    def plan(self, question):
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=self.catalog), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                side_effect=lambda catalog, question: (
                    catalog, {e["domain"] for e in catalog["entities"]
                              if e["domain"].lower() in question.lower()})), patch(
                "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                side_effect=lambda plan, index, mappings: plan):
            return plan_experimental_multihop(
                question, {}, [], model="test",
                ollama_host="http://localhost:11434", timeout=1,
                request_json=lambda *args: self.fail("No LLM call expected"))

    def test_b01_b05_zero_edge_select(self):
        for domain, label, prop in CASES:
            with self.subTest(domain=domain, property=prop):
                verb = "List" if prop == "MeasuredVariable" else (
                    "Show" if prop == "AssetName" else "Get")
                plan, selection = self.plan(
                    f"{verb} {prop} from {domain} {label}.")
                self.assertEqual(len(plan["entities"]), 1)
                self.assertEqual(plan["entities"][0]["domain"], domain)
                self.assertEqual(plan["edges"], [])
                self.assertEqual(plan["filters"], None)
                self.assertEqual(plan["operation"]["type"], "select")
                self.assertEqual(plan["projections"][0]["predicate"],
                                 "https://example.org/" + domain + "/has" + prop)
                self.assertEqual(selection["status"], "single_shape_grounded")

    def test_b06_uri_equality_filter(self):
        plan, selection = self.plan(
            "Show SignalName from opcuaconnectivity SignalMapping "
            "where AssetIdentifier is https://aas.example.com/FI103.")
        self.assertEqual(plan["edges"], [])
        self.assertEqual(plan["projections"][0]["predicate"],
                         "https://example.org/opcuaconnectivity/hasSignalName")
        self.assertEqual(plan["filters"], {
            "op": "eq", "entity": "n0",
            "predicate": "https://example.org/opcuaconnectivity/hasAssetIdentifier",
            "value": "https://aas.example.com/FI103",
        })
        self.assertEqual(selection["status"], "single_shape_grounded")

    def test_filter_without_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.plan("Get LocalId from dexpi InstrumentationFunction "
                      "where UnknownProperty is FI_103.")

    def test_unsupported_filter_cannot_be_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "Unsupported single-shape"):
            self.plan("Get LocalId from dexpi InstrumentationFunction "
                      "where LocalId contains FI_103.")

    def test_filter_literal_preserves_internal_dots(self):
        plan, _ = self.plan(
            "Show SignalName from opcuaconnectivity SignalMapping "
            "where AssetIdentifier is https://aas.example.com/FI.103.")
        self.assertEqual(plan["filters"]["value"],
                         "https://aas.example.com/FI.103")

    def test_unknown_output_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.plan("Get UnknownProperty from dexpi InstrumentationFunction.")

    def test_aggregation_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported single-shape"):
            self.plan("Count dexpi InstrumentationFunction entities.")


if __name__ == "__main__":
    unittest.main()
