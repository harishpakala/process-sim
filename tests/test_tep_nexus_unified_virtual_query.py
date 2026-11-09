"""Offline contract tests: Ollama cannot override query identity, bounds or SQL."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_unified_virtual_query import validate_contract, execute_question

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
QUESTION = ("For TI_101, retrieve measurements between 20 simulation seconds "
            "and 60, identify the associated engineering asset and provenance.")
REQUEST = {"engineering_function": "TI_101", "run_id": RUN,
           "start_simulation_seconds": 20, "end_simulation_seconds": 60,
           "limit": 1000}
PLAN = {"engineering_function": "TI_101", "operations": ["get_observations"]}


def fake_graph():
    f = "https://example.org/function/TI_101"
    s = "https://example.org/signal/XMEAS9"
    a = "https://example.org/asset/1"
    return {
        "nodes": [
            {"id": f, "type": "EngineeringFunction", "localId": "TI_101"},
            {"id": s, "type": "OperationalSignal", "signalId": "XMEAS9"},
            {"id": a, "type": "EngineeringAsset"},
            {"id": "obs1", "type": "VirtualObservation",
             "simulationTimeHours": 40 / 3600, "value": 1.0},
        ],
        "edges": [{"source": f, "predicate": "mapsToSignal", "target": s},
                  {"source": f, "predicate": "associatedWithAsset", "target": a}],
        "result": {"truncated": False},
        "provenance": {"physicalSensorBinding": "NOT_VERIFIED",
                       "sharedRunProvenance": "NOT_VERIFIED"},
        "observationIdentity": {"databasePrimaryKeyVerified": False},
    }


class UnifiedVirtualQueryTests(unittest.TestCase):
    def test_validated_contract_adds_mandatory_evidence_operators(self):
        result = validate_contract(PLAN, QUESTION, REQUEST, {"TI_101": {}})
        self.assertEqual(len(result["operations"]), 3)

    def test_rejects_mismatched_bounds(self):
        with self.assertRaisesRegex(ValueError, "interval differs"):
            validate_contract(PLAN, QUESTION, {**REQUEST, "end_simulation_seconds": 61},
                              {"TI_101": {}})

    def test_rejects_wrong_function_and_extra_fields(self):
        for raw in ({**PLAN, "engineering_function": "PI_101"},
                    {**PLAN, "sql": "DELETE FROM signal_samples"}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_contract(raw, QUESTION, REQUEST, {"TI_101": {}})

    def test_rejects_unsupported_operations(self):
        with self.assertRaises(ValueError):
            validate_contract({**PLAN, "operations": ["execute_sql"]},
                              QUESTION, REQUEST, {"TI_101": {}})

    def test_question_must_have_explicit_bounds(self):
        with self.assertRaises(ValueError):
            validate_contract(PLAN, "Show TI_101 measurements", REQUEST, {"TI_101": {}})

    def test_orchestration_returns_grounded_evidence(self):
        called = []
        def live(req, **kwargs):
            called.append(req)
            return fake_graph()
        result = execute_question(
            QUESTION, REQUEST, dsn="unused", graphdb_url="unused",
            ollama_url="unused",
            registry_loader=lambda *args: {"TI_101": {"operational_signal": "XMEAS9"}},
            planner=lambda *args: PLAN, live_executor=live)
        self.assertEqual(len(called), 1)
        self.assertEqual(result["evidence"]["observationCount"], 1)
        self.assertIn("NOT_VERIFIED", result["answer"])
        self.assertFalse(result["materializedInGraphDB"])


if __name__ == "__main__":
    unittest.main()
