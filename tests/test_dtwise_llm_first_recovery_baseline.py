"""Focused, offline recovery checks for the explicit llm_first route.

These checks do not claim that an Ollama model selects the correct IR.
They verify the routing and evidence-bound behavior with controlled LLM output.
"""
import json
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import plan_experimental_multihop


class LlmFirstRecoveryBaselineTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [{
            "domain": "opc", "shape": "urn:SignalMapping",
            "display_name": "SignalMapping",
            "properties": ["urn:hasAssetIdentifier", "urn:hasSignalName"],
        }], "shacl_edges": []}

    def plan(self, response):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(response)}}

        with patch(
            "process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
            return_value=self.catalog,
        ), patch(
            "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
            side_effect=lambda catalog, question: (catalog, {"opc"}),
        ), patch(
            "process_sim.dtwise.experimental_evidence_selection.resolve_shapes",
            side_effect=lambda plan, index, mappings: plan,
        ), patch(
            "process_sim.dtwise.experimental_multihop_cli._plan_single_shape_lookup",
            side_effect=AssertionError("hybrid shortcut used in llm_first"),
        ):
            plan, selection = plan_experimental_multihop(
                "List AssetIdentifier values with more than three opc SignalMapping entities.",
                {}, [], model="mock", ollama_host="http://localhost:11434",
                timeout=1, request_json=request, planning_mode="llm_first",
            )
        self.assertEqual(len(calls), 1)
        return plan, selection

    def test_grouped_having_llm_first_without_filter(self):
        plan, selection = self.plan({
            "path_id": "PATH_0", "operation": "group_count",
            "projections": ["N0P0"], "filter": None,
        })
        self.assertEqual(plan["operation"], {"type": "group_count", "having_min": 3})
        self.assertEqual(plan["projections"][0]["predicate"], "urn:hasAssetIdentifier")
        self.assertIsNone(plan["filters"])
        self.assertEqual(selection["choice"], "PATH_0")

    def test_llm_first_rejects_unrequested_substring_filter(self):
        with self.assertRaisesRegex(ValueError, "Unrequested substring filter"):
            self.plan({
                "path_id": "PATH_0", "operation": "group_count",
                "projections": ["N0P0"],
                "filter": {"property": "N0P0", "op": "contains", "value": "three"},
            })

    def test_llm_first_rejects_malformed_aggregate_filter(self):
        with self.assertRaisesRegex(ValueError, "Invalid evidence-selection filter"):
            self.plan({
                "path_id": "PATH_0", "operation": "group_count",
                "projections": ["N0P0"],
                "filter": {"property": "N0P0", "op": "gt", "value": 3},
            })


if __name__ == "__main__":
    unittest.main()
