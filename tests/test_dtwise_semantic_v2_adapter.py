"""Offline integration tests for v2 evidence-to-IR adapter."""
import json
import unittest
from unittest.mock import patch

from process_sim.dtwise.semantic_v2_adapter import (
    build_v2_candidates, select_and_bind_v2)


class SemanticV2AdapterTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [{
            "domain": "opc", "shape": "urn:SignalMapping",
            "display_name": "SignalMapping",
            "properties": ["urn:hasAssetIdentifier", "urn:hasSignalName"],
        }]}
        self.paths = [{"nodes": [("opc", "urn:SignalMapping")], "steps": []}]
        self.selection = {
            "path_id": "PATH_0", "operation": "select",
            "projections": ["N0P1"], "group_by": [],
            "count_target": None, "aggregate_condition": None, "filters": [],
        }

    def run_plan(self, selection):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(selection)}}
        with patch(
            "process_sim.dtwise.semantic_v2_adapter.resolve_shapes",
            side_effect=lambda plan, index, mappings: plan,
        ):
            result = select_and_bind_v2(
                "Get SignalName from OPCUAConnectivity",
                self.paths, self.catalog, {}, [],
                model="mock", request_json=request,
                ollama_host="http://localhost:11434", timeout=1)
        return result, calls

    def test_evidence_candidate_identifiers(self):
        candidates = build_v2_candidates(self.paths, self.catalog)
        self.assertEqual(candidates[0]["nodes"][0]["id"], "N0")
        self.assertEqual(candidates[0]["properties"][1]["id"], "N0P1")

    def test_basic_select_binds_verified_predicate(self):
        (plan, selected), calls = self.run_plan(self.selection)
        self.assertEqual(len(calls), 1)
        self.assertEqual(selected["path_id"], "PATH_0")
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasSignalName")
        self.assertEqual(plan["operation"], {"type": "select"})

    def test_group_count_having_is_preserved(self):
        selection = {**self.selection, "operation": "group_count",
                     "projections": ["N0P0"], "group_by": ["N0P0"],
                     "count_target": "N0",
                     "aggregate_condition": {"operator": "gt", "value": 3}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["operation"], {"type": "group_count", "having_min": 3})
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasAssetIdentifier")

    def test_multihop_count_selected_terminal_entity(self):
        second = {"domain": "opc", "shape": "urn:Device",
                  "display_name": "Device", "properties": ["urn:hasDeviceId"]}
        self.catalog["entities"].append(second)
        step = {"kind": "shacl", "predicate": "urn:hasDevice"}
        self.paths = [{"nodes": [("opc", "urn:SignalMapping"),
                                  ("opc", "urn:Device")], "steps": [step]}]
        selection = {**self.selection, "operation": "count",
                     "projections": [], "count_target": "N1"}
        with patch("process_sim.dtwise.evidence_path_binding.enumerate_evidenced_paths",
                   return_value=self.paths):
            (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["operation"],
                         {"type": "count", "count_entity": "n1"})
        self.assertEqual(plan["edges"][0]["predicate"], "urn:hasDevice")
        self.assertEqual(plan["projections"], [])

    def test_multihop_group_count_selected_terminal_entity(self):
        second = {"domain": "opc", "shape": "urn:Device",
                  "display_name": "Device", "properties": ["urn:hasDeviceId"]}
        self.catalog["entities"].append(second)
        step = {"kind": "shacl", "predicate": "urn:hasDevice"}
        self.paths = [{"nodes": [("opc", "urn:SignalMapping"),
                                  ("opc", "urn:Device")], "steps": [step]}]
        selection = {**self.selection, "operation": "group_count",
                     "projections": ["N0P0"], "group_by": ["N0P0"],
                     "count_target": "N1",
                     "aggregate_condition": {"operator": "gt", "value": 2}}
        with patch("process_sim.dtwise.evidence_path_binding.enumerate_evidenced_paths",
                   return_value=self.paths):
            (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["operation"],
                         {"type": "group_count", "count_entity": "n1",
                          "having_min": 2})

    def test_distinct_property_count(self):
        selection = {**self.selection, "operation": "count",
                     "projections": [], "count_target": "N0",
                     "distinct": True, "count_property": "N0P1"}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["operation"], {"type": "count"})
        self.assertEqual(plan["count_distinct_property"], {
            "entity": "n0", "predicate": "urn:hasSignalName"})

    def test_distinct_count_requires_evidenced_property(self):
        selection = {**self.selection, "operation": "count",
                     "projections": [], "count_target": "N0",
                     "distinct": True, "count_property": "N0P99"}
        with self.assertRaisesRegex(ValueError, "after two attempts"):
            self.run_plan(selection)

    def test_literal_equality_filter(self):
        selection = {**self.selection, "filters": [
            {"property": "N0P0", "op": "eq", "value": "FI103"}]}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"], {
            "op": "eq", "entity": "n0",
            "predicate": "urn:hasAssetIdentifier", "value": "FI103"})
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasSignalName")

    def test_order_and_limit(self):
        selection = {**self.selection,
                     "order_by": {"property": "N0P1", "direction": "desc"},
                     "limit": 5}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["order_by"], [{"as": "value0", "direction": "desc"}])
        self.assertEqual(plan["result_limit"], 5)

    def test_reject_ordering_by_unprojected_property(self):
        selection = {**self.selection,
                     "order_by": {"property": "N0P0", "direction": "desc"}}
        with self.assertRaisesRegex(ValueError, "must be projected"):
            self.run_plan(selection)

    def test_reject_non_gt_having(self):
        selection = {**self.selection, "operation": "group_count",
                     "projections": ["N0P0"], "group_by": ["N0P0"],
                     "count_target": "N0",
                     "aggregate_condition": {"operator": "gte", "value": 3}}
        with self.assertRaisesRegex(ValueError, "not yet supported"):
            self.run_plan(selection)

    def test_boolean_exists_and_missing(self):
        selection = {**self.selection,
                     "where": {"op": "and", "conditions": [
                         {"op": "exists", "property": "N0P0"},
                         {"op": "missing", "property": "N0P1"}]}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"]["op"], "and")
        self.assertEqual(plan["filters"]["children"][0]["op"], "exists")
        self.assertEqual(plan["filters"]["children"][1]["op"], "not_exists")

    def test_boolean_or_and_negated_exists(self):
        selection = {**self.selection,
                     "where": {"op": "or", "conditions": [
                         {"op": "exists", "property": "N0P0"},
                         {"op": "not", "condition": {
                             "op": "exists", "property": "N0P1"}}]}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"]["op"], "or")
        self.assertEqual(plan["filters"]["children"][1]["op"], "not_exists")

    def test_empty_projection_returns_evidenced_entities(self):
        selection = {**self.selection, "projections": [],
                     "where": {"op": "exists", "property": "N0P0"}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertTrue(plan["return_entities"])
        self.assertEqual(plan["filters"]["predicate"], "urn:hasAssetIdentifier")

    def test_contains_ignore_case(self):
        selection = {**self.selection, "where": {
            "op": "contains", "property": "N0P1", "value": "reactor",
            "ignore_case": True}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"]["op"], "contains")
        self.assertTrue(plan["filters"]["ignore_case"])

    def test_regex_is_bound_to_evidenced_property(self):
        selection = {**self.selection,
                     "where": {"op": "regex", "property": "N0P0",
                               "value": "^FI-"}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"]["op"], "regex")
        self.assertEqual(plan["filters"]["predicate"], "urn:hasAssetIdentifier")
        self.assertEqual(plan["filters"]["value"], "^FI-")

    def test_prefix_is_bound_to_evidenced_property(self):
        selection = {**self.selection,
                     "where": {"op": "starts_with", "property": "N0P1",
                               "value": "XMEAS"}}
        (plan, _), _calls = self.run_plan(selection)
        self.assertEqual(plan["filters"]["op"], "starts_with")
        self.assertEqual(plan["filters"]["value"], "XMEAS")


if __name__ == "__main__":
    unittest.main()
