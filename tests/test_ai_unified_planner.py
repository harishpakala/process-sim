"""Offline tests for validated semantic-temporal routing."""

# Created: 2026-10-23
# Author: Harish
import json
import unittest
from process_sim.ai.unified_planner import query_unified

RUN = "c2e5a121-99f8-4d19-b0b5-15cefe5bd611"

def model(route, plan):
    return lambda url, body: {"message": {"content": json.dumps({"route": route, "plan": plan})}}

class RoutingTests(unittest.TestCase):
    def test_temporal(self):
        result = query_unified("show samples", "unused",
            ollama_transport=model("temporal", {"operation": "signal_history",
                "runId": RUN, "signal": "XMEAS1", "limit": 20}),
            temporal_executor=lambda plan: {"signal": plan["signal"]})
        self.assertEqual(result["data"]["signal"], "XMEAS1")

    def test_missing_context(self):
        result = query_unified("show samples", "unused",
            ollama_transport=model("insufficient", None))
        self.assertEqual(result["status"], "insufficient_schema")

    def test_engineering(self):
        result = query_unified("show assets", "unused",
            ollama_transport=model("engineering", None),
            engineering_executor=lambda *args, **kwargs: {"status": "delegated"})
        self.assertEqual(result["status"], "delegated")
