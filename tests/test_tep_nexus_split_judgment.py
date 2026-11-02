"""Offline checks for split numerical and engineering judgment."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_split_judgment import validate_numerical, validate_interpretation

EVIDENCE = {"comparison": {
    "series": [
        {"engineering_function": "FI_101", "relative_endpoint_change_percent": -0.20088058804540695},
        {"engineering_function": "PI_101", "relative_endpoint_change_percent": 0.010290357685705524},
    ],
    "larger_absolute_relative_change_index": 0,
}}
NUMERICAL = {
    "engineering_functions": ["FI_101", "PI_101"],
    "relative_change_magnitudes_percent": [0.20088058804540695, 0.010290357685705524],
    "larger_absolute_relative_change_function": "FI_101",
    "numerical_conclusion": "FI_101 has the larger absolute relative change.",
}
INTERPRETATION = {
    "numerical_conclusion": NUMERICAL["numerical_conclusion"],
    "engineering_interpretation": "This numerical comparison is supported, but physical process claims are not verified.",
    "limitations": ["Provisional engineering mapping", "Unverified physical sensor binding",
                    "Unverified shared run provenance", "Unsupported causal inference"],
    "causal_inference_supported": False,
    "physical_binding_verified": False,
    "shared_run_provenance_verified": False,
}

class TestSplitJudgment(unittest.TestCase):
    def test_numerical_correct(self):
        self.assertEqual(validate_numerical(NUMERICAL, EVIDENCE)["failed_checks"], [])

    def test_wrong_winner_detected(self):
        bad = dict(NUMERICAL, larger_absolute_relative_change_function="PI_101")
        self.assertIn("winner", validate_numerical(bad, EVIDENCE)["failed_checks"])

    def test_wrong_magnitude_detected(self):
        bad = dict(NUMERICAL, relative_change_magnitudes_percent=[0.01029, 0.20088])
        self.assertIn("magnitudes", validate_numerical(bad, EVIDENCE)["failed_checks"])

    def test_interpretation_correct(self):
        self.assertEqual(validate_interpretation(INTERPRETATION, NUMERICAL, EVIDENCE)["failed_checks"], [])

    def test_inconclusive_revision_detected(self):
        bad = dict(INTERPRETATION, numerical_conclusion="The comparison is inconclusive.")
        self.assertIn("numerical_conclusion_retained",
                      validate_interpretation(bad, NUMERICAL, EVIDENCE)["failed_checks"])

    def test_provenance_false_claim_detected(self):
        bad = dict(INTERPRETATION, physical_binding_verified=True)
        self.assertIn("provenance_flags", validate_interpretation(bad, NUMERICAL, EVIDENCE)["failed_checks"])

if __name__ == "__main__":
    unittest.main()
