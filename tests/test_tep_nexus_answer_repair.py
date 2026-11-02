"""Offline checks for deterministic answer reconstruction."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_answer_repair import repair_answer

EVIDENCE = {
    "engineering_function": "TI_101",
    "latest_persisted_observation": {
        "simulation_seconds": 3514.0,
        "value": 120.38819508324035,
        "record_age_seconds": 28110.715,
    },
    "associated_asset_uri": "urn:asset:sample",
    "quantitative_temporal_analytics": {
        "status": "OK",
        "mean": 120.39743498080082,
        "standard_deviation_population": 0.010536816882043902,
        "linear_regression_slope_per_simulation_minute": -0.00016489704340073697,
        "endpoint_change": -0.013186998604481914,
        "history_truncated_by_limit": False,
    },
}


class TestAnswerRepair(unittest.TestCase):
    def test_reconstructs_failed_answer(self):
        original = {"answer": "The trend is provisional.", "limitations": []}
        result = repair_answer(original, EVIDENCE)
        self.assertTrue(result["repair_success"], result["repaired_validation"]["failed_checks"])
        self.assertEqual(result["original_answer"], original)
        self.assertIn("endpoint change -0.013186998604481914", result["repaired_answer"]["answer"])
        self.assertNotIn("trend is provisional", result["repaired_answer"]["answer"])

    def test_preserves_original(self):
        original = {"answer": "Incorrect latest measurement 999", "limitations": []}
        result = repair_answer(original, EVIDENCE)
        self.assertEqual(result["original_answer"], original)
        self.assertNotIn("999", result["repaired_answer"]["answer"])

    def test_truncated_history_disclosed(self):
        evidence = dict(EVIDENCE)
        evidence["quantitative_temporal_analytics"] = dict(
            EVIDENCE["quantitative_temporal_analytics"],
            history_truncated_by_limit=True,
        )
        result = repair_answer({"answer": "", "limitations": []}, evidence)
        self.assertTrue(result["repair_success"], result["repaired_validation"]["failed_checks"])
        self.assertTrue(any("truncated" in x for x in result["repaired_answer"]["limitations"]))

    def test_without_history(self):
        evidence = dict(EVIDENCE)
        evidence.pop("quantitative_temporal_analytics")
        result = repair_answer({"answer": "", "limitations": []}, evidence)
        self.assertTrue(result["repair_success"], result["repaired_validation"]["failed_checks"])

    def test_not_stale(self):
        evidence = dict(EVIDENCE)
        evidence["latest_persisted_observation"] = dict(
            EVIDENCE["latest_persisted_observation"], record_age_seconds=1.0
        )
        result = repair_answer({"answer": "", "limitations": []}, evidence)
        self.assertTrue(result["repair_success"], result["repaired_validation"]["failed_checks"])
        self.assertFalse(any("stale" in x for x in result["repaired_answer"]["limitations"]))


if __name__ == "__main__":
    unittest.main()
