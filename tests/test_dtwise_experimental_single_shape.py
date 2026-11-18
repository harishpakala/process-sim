"""Offline tests for one-call experimental single-shape semantic planning."""
import json
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import plan_experimental_multihop


class ExperimentalSingleShapeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [{
            "domain": "opc", "shape": "urn:Signal", "display_name": "Signal",
            "properties": ["urn:hasSignalName", "urn:hasAssetIdentifier",
                           "urn:hasOPCUANodeId"]}], "shacl_edges": []}

    def plan(self, question, response):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(response)}}
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=self.catalog), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                side_effect=lambda catalog, question: (catalog, {"opc"})), patch(
                "process_sim.dtwise.experimental_evidence_selection.resolve_shapes",
                side_effect=lambda plan, index, mappings: plan):
            result = plan_experimental_multihop(
                question, {}, [], model="test", ollama_host="http://localhost:11434",
                timeout=1, request_json=request)
        self.assertEqual(len(calls), 1)
        return result

    def test_basic_select_calls_llm(self):
        plan, info = self.plan("Get SignalName from opc Signal.", {
            "path_id": "PATH_0", "operation": "select", "projections": ["N0P0"], "filter": None})
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasSignalName")
        self.assertEqual(info["status"], "evidence_semantic_grounded")

    def test_multiple_projections(self):
        plan, _ = self.plan("Get SignalName and OPCUANodeId from opc Signal.", {
            "path_id": "PATH_0", "operation": "select", "projections": ["N0P0", "N0P2"], "filter": None})
        self.assertEqual(len(plan["projections"]), 2)

    def test_equality_filter(self):
        plan, _ = self.plan("Show SignalName from opc Signal where AssetIdentifier is FI103.", {
            "path_id": "PATH_0", "operation": "select", "projections": ["N0P0"],
            "filter": {"property": "N0P1", "op": "eq", "value": "FI103"}})
        self.assertEqual(plan["filters"]["predicate"], "urn:hasAssetIdentifier")

    def test_exact_uri_filter_value_preserved(self):
        uri = "https://aas.example.com/FI103"
        plan, _ = self.plan(
            "Show SignalName from opc Signal where AssetIdentifier is " + uri + ".",
            {"path_id": "PATH_0", "operation": "select",
             "projections": ["N0P0"],
             "filter": {"property": "N0P1", "op": "eq",
                        "value": "https://aas.example.com/FI103."}})
        self.assertEqual(plan["filters"]["value"], uri)

    def test_wrong_filter_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "different equality-filter property"):
            self.plan(
                "Show SignalName from opc Signal where AssetIdentifier is FI103.",
                {"path_id": "PATH_0", "operation": "select",
                 "projections": ["N0P0"],
                 "filter": {"property": "N0P2", "op": "eq", "value": "FI103"}})

    def test_omitted_model_filter_grounded_from_explicit_question(self):
        plan, _ = self.plan(
            "Get SignalName from opc Signal where AssetIdentifier is FI103.",
            {"path_id": "PATH_0", "operation": "select",
             "projections": ["N0P0"], "filter": None})
        self.assertEqual(plan["filters"]["predicate"], "urn:hasAssetIdentifier")
        self.assertEqual(plan["filters"]["value"], "FI103")

    def test_invented_filter_rejected(self):
        with self.assertRaisesRegex(ValueError, "invented an equality filter"):
            self.plan(
                "Get SignalName from opc Signal matched by AssetIdentifier.",
                {"path_id": "PATH_0", "operation": "select",
                 "projections": ["N0P0"],
                 "filter": {"property": "N0P1", "op": "eq",
                            "value": "literal"}})

    def test_invented_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "invented"):
            self.plan("Get SignalName from opc Signal.", {
                "path_id": "PATH_0", "operation": "select", "projections": ["N0P999"], "filter": None})

    def test_unsupported_operation_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.plan("Count opc Signal entities.", {
                "path_id": None, "operation": "unsupported", "projections": [], "filter": None})


if __name__ == "__main__":
    unittest.main()
