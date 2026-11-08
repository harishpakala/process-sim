"""Offline tests for semantic-temporal evaluation cases and overlap integrity."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_semantic_temporal_evaluation import evaluate

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"


def make_graph(request, *, change_id=False, truncated=False):
    start, end = request["start_simulation_seconds"], request["end_simulation_seconds"]
    f, s, a = "function", "signal", "asset"
    observations = []
    for second in (20, 30, 40):
        if start <= second <= end:
            observations.append({
                "id": "changed" if change_id and second == 30 else f"obs{second}",
                "type": "VirtualObservation", "identityScope": "CONTENT_FINGERPRINT_NOT_DATABASE_PRIMARY_KEY",
                "simulationTimeHours": second / 3600, "value": second})
    return {
        "nodes": [{"id": "function", "type": "EngineeringFunction", "localId": "TI_101"},
                  {"id": "signal", "type": "OperationalSignal"},
                  {"id": "asset", "type": "EngineeringAsset"}] + observations,
        "edges": [{"source": "function", "predicate": "mapsToSignal", "target": "signal"},
                  {"source": "function", "predicate": "associatedWithAsset", "target": "asset"}],
        "result": {"observationCount": len(observations), "truncated": truncated},
        "provenance": {"physicalSensorBinding": "NOT_VERIFIED",
                       "sharedRunProvenance": "NOT_VERIFIED"},
        "materializedInGraphDB": False,
    }


class EvaluationTests(unittest.TestCase):
    def run_eval(self, executor, windows=None):
        return evaluate(RUN, windows or [[20, 40], [25, 35]],
                        dsn="unused", graphdb_url="unused",
                        registry_loader=lambda *args: {"TI_101": {}},
                        executor=executor, clock=lambda: 1.0)

    def test_pass_and_cross_window_identity(self):
        result = self.run_eval(lambda req, **kwargs: make_graph(req))
        self.assertEqual(result["summary"]["status"], "PASS")
        self.assertEqual(result["summary"]["passedCases"], 2)
        self.assertEqual(result["summary"]["overlapChecksPassed"], 1)

    def test_detects_cross_window_identity_mismatch(self):
        result = self.run_eval(
            lambda req, **kwargs: make_graph(req, change_id=req["start_simulation_seconds"] == 25))
        self.assertEqual(result["summary"]["status"], "FAIL")
        self.assertEqual(result["summary"]["overlapChecksFailed"], 1)

    def test_truncated_overlap_not_misreported_as_consistent(self):
        result = self.run_eval(lambda req, **kwargs: make_graph(req, truncated=True))
        self.assertEqual(result["overlapChecks"][0]["status"], "NOT_ASSESSED_TRUNCATED")

    def test_failure_is_reported_not_swallowed(self):
        def fail(*args, **kwargs):
            raise RuntimeError("offline test failure")
        result = self.run_eval(fail)
        self.assertEqual(result["summary"]["failedOrErroredCases"], 2)
        self.assertEqual(result["summary"]["status"], "FAIL")

    def test_invalid_function_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(RUN, [[20, 40]], dsn="unused", graphdb_url="unused",
                     functions=["UNKNOWN"],
                     registry_loader=lambda *args: {"TI_101": {}})


if __name__ == "__main__":
    unittest.main()
