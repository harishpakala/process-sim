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

    def test_invented_filter_is_ignored(self):
        plan, _ = self.plan(
            "Get SignalName from opc Signal matched by AssetIdentifier.",
            {"path_id": "PATH_0", "operation": "select",
             "projections": ["N0P0"],
             "filter": {"property": "N0P1", "op": "eq",
                        "value": "literal"}})
        self.assertIsNone(plan["filters"])

    def test_invented_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "invented"):
            self.plan("Get SignalName from opc Signal.", {
                "path_id": "PATH_0", "operation": "select", "projections": ["N0P999"], "filter": None})

    def test_count_entities(self):
        plan, _ = self.plan("Count opc Signal entities.", {
            "path_id": "PATH_0", "operation": "count",
            "projections": [], "filter": None})
        self.assertEqual(plan["operation"]["type"], "count")
        self.assertEqual(plan["projections"], [])

    def test_grouped_count(self):
        plan, _ = self.plan("Count opc Signal entities for each AssetIdentifier.", {
            "path_id": "PATH_0", "operation": "group_count",
            "projections": ["N0P1"], "filter": None})
        self.assertEqual(plan["operation"]["type"], "group_count")
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasAssetIdentifier")

    def test_grouped_count_having(self):
        plan, _ = self.plan("List AssetIdentifier values with more than three opc Signal entities.", {
            "path_id": "PATH_0", "operation": "group_count",
            "projections": ["N0P1"], "filter": None})
        self.assertEqual(plan["operation"]["having_min"], 3)

    def test_grouped_having_recovers_model_select(self):
        plan, _ = self.plan(
            "List AssetIdentifier values with more than three opc Signal entities.",
            {"path_id": "PATH_0", "operation": "select",
             "projections": ["N0P1"], "filter": None})
        self.assertEqual(plan["operation"], {"type": "group_count", "having_min": 3})

    def test_grouped_having_rejects_unrequested_group_key(self):
        with self.assertRaisesRegex(ValueError, "key is not requested"):
            self.plan(
                "List AssetIdentifier values with more than three opc Signal entities.",
                {"path_id": "PATH_0", "operation": "select",
                 "projections": ["N0P0"], "filter": None})

    def test_sorted_limited_select(self):
        plan, _ = self.plan("Get the first ten SignalName values from opc Signal in ascending alphabetical order.", {
            "path_id": "PATH_0", "operation": "select",
            "projections": ["N0P0"], "filter": None})
        self.assertEqual(plan["result_limit"], 10)
        self.assertEqual(plan["order_by"], [{"as": "value_0", "direction": "asc"}])

    def test_unsupported_operation_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported evidence-selection operation"):
            self.plan("Count opc Signal entities.", {
                "path_id": None, "operation": "unsupported", "projections": [], "filter": None})


if __name__ == "__main__":
    unittest.main()
