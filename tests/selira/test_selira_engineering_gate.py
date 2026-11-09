"""Deterministic SELiRA engineering-gate cases (no GraphDB or Ollama required)."""

# Created: 2026-10-30
# Author: Harish
import copy
import unittest

from process_sim.selira.engineering_gate import evaluate_engineering_use


def fixture():
    nodes = {"DEXPI": "instrument:P7", "ECAD": "device:P7",
             "PLC": "channel:P7", "OPCUA": "node:P7", "TEP": "XMEAS7"}
    roles = list(nodes)
    edges = [{"from": nodes[roles[i]], "to": nodes[roles[i + 1]],
              "evidence": "urn:reviewed:edge:" + str(i), "revision": "r1"}
             for i in range(4)]
    snapshot = {"revision": "r1", "lifecycle": "CURRENT", "runId": "run1",
                "coverage": [0, 100],
                "paths": [{"nodes": nodes, "edges": edges, "signal": "XMEAS7",
                           "property": "reactorPressure",
                           "engineeringQuantityKind": "pressure",
                           "signalQuantityKind": "pressure",
                           "engineeringUnit": "kPa", "signalUnit": "kPa"}],
                "observation": {"signal": "XMEAS7", "runId": "run1",
                                "revision": "r1", "time": 50, "value": 2700.0}}
    task = {"revision": "r1", "runId": "run1", "interval": [40, 60],
            "signal": "XMEAS7", "property": "reactorPressure",
            "question": "What is the reactor pressure?"}
    return snapshot, task


class EngineeringGateTests(unittest.TestCase):
    def test_valid_snapshot(self):
        s, t = fixture()
        self.assertTrue(evaluate_engineering_use(s, t).allowed)

    def test_wrong_quantity(self):
        s, t = fixture()
        s["paths"][0]["signalQuantityKind"] = "temperature"
        self.assertEqual(evaluate_engineering_use(s, t).status, "F")

    def test_wrong_unit(self):
        s, t = fixture()
        s["paths"][0]["signalUnit"] = "K"
        self.assertEqual(evaluate_engineering_use(s, t).status, "F")

    def test_duplicate_mapping(self):
        s, t = fixture()
        s["paths"].append(copy.deepcopy(s["paths"][0]))
        self.assertEqual(evaluate_engineering_use(s, t).status, "F")

    def test_missing_mapping(self):
        s, t = fixture()
        s["paths"][0]["edges"].pop()
        self.assertEqual(evaluate_engineering_use(s, t).status, "U")

    def test_pending_revision(self):
        s, t = fixture()
        s["lifecycle"] = "PENDING"
        self.assertFalse(evaluate_engineering_use(s, t).allowed)

    def test_stale_revision(self):
        s, t = fixture()
        t["revision"] = "r2"
        self.assertFalse(evaluate_engineering_use(s, t).allowed)

    def test_insufficient_coverage(self):
        s, t = fixture()
        t["interval"] = [40, 110]
        self.assertEqual(evaluate_engineering_use(s, t).status, "F")

    def test_missing_run_provenance(self):
        s, t = fixture()
        s["runId"] = None
        self.assertFalse(evaluate_engineering_use(s, t).allowed)


if __name__ == "__main__":
    unittest.main()
