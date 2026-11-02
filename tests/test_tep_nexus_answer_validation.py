"""Offline tests for conservative evidence-based answer checks."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_answer_validation import validate_answer

EVIDENCE = {
    "engineering_function": "TI_101",
    "latest_persisted_observation": {"value": 120.5, "record_age_seconds": 600},
    "associated_asset_uri": "urn:test:asset",
    "quantitative_temporal_analytics": {
        "status": "OK", "mean": 120.4, "standard_deviation_population": 0.1,
        "linear_regression_slope_per_simulation_minute": -0.02,
        "endpoint_change": -0.3, "history_truncated_by_limit": False,
    },
}
GOOD = {
    "answer": ("TI_101 latest measurement is 120.5. Asset urn:test:asset. "
               "Mean 120.4, standard deviation 0.1, regression slope -0.02 "
               "signal value per simulation minute, endpoint change -0.3. "
               "The latest persisted record is stale."),
    "limitations": ["Engineering mapping is provisional.",
                    "Shared run provenance is unverified."],
}

class TestAnswerValidation(unittest.TestCase):
    def test_supported_answer(self):
        self.assertEqual(validate_answer(GOOD, EVIDENCE)["status"], "CHECKS_PASSED_LIMITED_SCOPE")

    def test_wrong_latest(self):
        a = dict(GOOD, answer=GOOD["answer"].replace("120.5", "130.5"))
        self.assertIn("latest_value", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_wrong_slope(self):
        a = dict(GOOD, answer=GOOD["answer"].replace("-0.02", "0.02"))
        self.assertIn("linear_regression_slope", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_missing_endpoint(self):
        a = dict(GOOD, answer=GOOD["answer"].replace("endpoint change -0.3", ""))
        self.assertIn("endpoint_change", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_stale_disclosure(self):
        a = dict(GOOD, answer=GOOD["answer"].replace("is stale", "was retrieved"))
        self.assertIn("stale_record_disclosure", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_mapping_trend_conflation(self):
        a = dict(GOOD, answer=GOOD["answer"] + " The trend is provisional.")
        self.assertIn("no_trend_mapping_conflation", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_missing_provenance(self):
        a = dict(GOOD, limitations=["Engineering mapping is provisional."])
        self.assertIn("shared_run_provenance", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_wrong_asset(self):
        a = dict(GOOD, answer=GOOD["answer"].replace("urn:test:asset", "urn:test:other"))
        self.assertIn("asset_uri", validate_answer(a, EVIDENCE)["failed_checks"])

    def test_truncated(self):
        e = dict(EVIDENCE, quantitative_temporal_analytics=dict(EVIDENCE["quantitative_temporal_analytics"], history_truncated_by_limit=True))
        self.assertIn("history_truncation", validate_answer(GOOD, e)["failed_checks"])

    def test_no_unqualified_live(self):
        a = dict(GOOD, answer=GOOD["answer"] + " This is a live sensor reading.")
        self.assertIn("no_unqualified_live_claim", validate_answer(a, EVIDENCE)["failed_checks"])


if __name__ == "__main__":
    unittest.main()
