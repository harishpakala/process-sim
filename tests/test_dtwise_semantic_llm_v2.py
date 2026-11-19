"""Offline tests for the independent v2 LLM/evidence boundary."""
import json
import unittest

from process_sim.dtwise.semantic_llm_v2 import select_semantic_v2


class SemanticLlmV2Tests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"id": "PATH_0", "nodes": [{"id": "N0", "shape": "SignalMapping"}],
             "steps": [], "properties": [
                 {"id": "N0P0", "label": "AssetIdentifier"},
                 {"id": "N0P1", "label": "SignalName"}]},
            {"id": "PATH_1", "nodes": [{"id": "N0", "shape": "Other"}],
             "steps": [], "properties": [
                 {"id": "N0P0", "label": "OtherProperty"}]},
        ]
        self.valid = {
            "path_id": "PATH_0", "operation": "group_count",
            "projections": ["N0P0"], "group_by": ["N0P0"],
            "count_target": "N0",
            "aggregate_condition": {"operator": "gt", "value": 3},
            "filters": [],
        }

    def run_selection(self, outputs, *, diagnostics=None):
        requests = []
        def request(url, payload, timeout):
            requests.append(payload)
            index = len(requests) - 1
            return {"message": {"content": json.dumps(outputs[index])}}
        result = select_semantic_v2(
            "List identifiers with more than three mappings",
            self.candidates, model="mock", request_json=request,
            ollama_host="http://localhost:11434", timeout=1,
            diagnostics=diagnostics)
        return result, requests

    def test_valid_selection_one_call(self):
        result, calls = self.run_selection([self.valid])
        self.assertEqual(result["operation"], "group_count")
        self.assertEqual(len(calls), 1)

    def test_compact_prompt_preserves_all_selection_ids(self):
        _, calls = self.run_selection([self.valid])
        user = json.loads(calls[0]["messages"][1]["content"])
        self.assertEqual(len(user["evidence_paths"]), 2)
        self.assertEqual(user["evidence_paths"][0][0], "PATH_0")
        self.assertEqual(user["evidence_paths"][0][1][0][0], "N0")
        self.assertEqual(
            [p[0] for p in user["evidence_paths"][0][2]],
            ["N0P0", "N0P1"])
        self.assertEqual(user["evidence_paths"][0][2][1][1], "SignalName")

    def test_repair_after_invalid_filter(self):
        invalid = {**self.valid, "filters": [
            {"property": "N0P1", "op": "gt", "value": "3"}]}
        diagnostics = {}
        result, calls = self.run_selection([invalid, self.valid],
                                           diagnostics=diagnostics)
        self.assertEqual(result["aggregate_condition"]["value"], 3)
        self.assertEqual(len(calls), 2)
        self.assertIn("strict evidence validation", calls[1]["messages"][-1]["content"])
        self.assertEqual(diagnostics["semantic_v2_attempts"][0]["status"], "rejected")
        self.assertEqual(diagnostics["semantic_v2_attempts"][1]["status"], "accepted")

    def test_reject_property_not_on_selected_path(self):
        invalid = {**self.valid, "path_id": "PATH_1",
                   "projections": ["N0P1"], "group_by": ["N0P1"]}
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(invalid)}}
        with self.assertRaisesRegex(ValueError, "after two attempts"):
            select_semantic_v2(
                "question", self.candidates, model="mock",
                request_json=request, ollama_host="http://localhost:11434",
                timeout=1)
        self.assertEqual(len(calls), 2)

    def test_reject_missing_path_without_fallback(self):
        invalid = {**self.valid, "path_id": None}
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(invalid)}}
        with self.assertRaisesRegex(ValueError, "Missing or invalid evidence path"):
            select_semantic_v2(
                "question", self.candidates, model="mock",
                request_json=request, ollama_host="http://localhost:11434",
                timeout=1)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
