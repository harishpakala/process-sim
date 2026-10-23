"""Offline evidence and abstention tests for engineering-temporal workflow."""
import unittest
from process_sim.ai.semantic_temporal_workflow import execute_asset_signal_workflow

RUN = "c2e5a121-99f8-4d19-b0b5-15cefe5bd611"
PLAN = {"operation": "asset_history", "runId": RUN,
        "assetIri": "https://example.org/asset/1", "limit": 10}

class WorkflowTests(unittest.TestCase):
    def test_mapped(self):
        def reader(asset, run, limit):
            return {"status": "mapped", "signal": "XMEAS1",
                    "signals": ["XMEAS1"], "references": ["opcua/XMEAS1"],
                    "points": [{"time": 1, "value": 7}], "faultEvents": []}
        result = execute_asset_signal_workflow(PLAN, asset_reader=reader)
        self.assertEqual(result["mappingStatus"], "mapped")
        self.assertEqual(result["evidence"]["operationalReferences"], ["opcua/XMEAS1"])

    def test_ambiguous(self):
        result = execute_asset_signal_workflow(PLAN, asset_reader=lambda a, r, l: {
            "status": "ambiguous", "signals": ["XMEAS1", "XMEAS2"],
            "references": ["XMEAS1", "XMEAS2"], "points": []})
        self.assertEqual(result["status"], "insufficient_mapping")
        self.assertEqual(result["points"], [])

    def test_invalid_mapping_evidence(self):
        with self.assertRaises(ValueError):
            execute_asset_signal_workflow(PLAN, asset_reader=lambda a, r, l: {
                "status": "mapped", "signal": "XMEAS1", "signals": []})
