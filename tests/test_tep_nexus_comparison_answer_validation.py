"""Offline evidence-coverage checks for comparison answer validation."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_comparison_answer_validation import validate_comparison_answer


EVIDENCE = {"comparison": {
    "common_start_simulation_seconds": 2916.0,
    "common_end_simulation_seconds": 3514.0,
    "comparison_available": True,
    "larger_absolute_relative_change_index": 0,
    "series": [
        {"engineering_function": "FI_101", "endpoint_change": -0.000503544571995751,
         "relative_endpoint_change_percent": -0.20088058804540695},
        {"engineering_function": "PI_101", "endpoint_change": 0.27829719819646925,
         "relative_endpoint_change_percent": 0.010290357685705524},
    ],
}}
LIMITS = ["Engineering mapping is provisional.", "Physical sensor binding is not verified.",
          "Shared run provenance is unverified."]
FULL = {"answer": ("FI_101 changed more than PI_101 in simulation time 2916 to 3514 seconds. "
                   "FI_101 endpoint change -0.00050354, relative -0.2009%; "
                   "PI_101 endpoint change 0.2782972, relative 0.0103%."),
        "limitations": LIMITS}


class TestComparisonAnswerValidation(unittest.TestCase):
    def test_complete_evidence_coverage(self):
        result = validate_comparison_answer(FULL, EVIDENCE)
        self.assertEqual(result["failed_checks"], [])
        self.assertEqual(result["status"], "CHECKS_PASSED_LIMITED_SCOPE")

    def test_previous_short_answer_fails_completeness(self):
        answer = {"answer": "FI_101 changed more relative to its initial value",
                  "limitations": ["provisional mapping", "physical sensor binding not verified",
                                  "causal inference not supported"]}
        result = validate_comparison_answer(answer, EVIDENCE)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("relative_changes", result["failed_checks"])
        self.assertIn("shared_provenance_unverified", result["failed_checks"])

    def test_wrong_winner_fails(self):
        answer = dict(FULL, answer=FULL["answer"].replace(
            "FI_101 changed more than PI_101", "PI_101 changed more than FI_101"))
        self.assertIn("correct_winner", validate_comparison_answer(answer, EVIDENCE)["failed_checks"])

    def test_causal_assertion_fails(self):
        answer = dict(FULL, answer=FULL["answer"] + " PI_101 caused the FI_101 change.")
        self.assertIn("no_causal_claim", validate_comparison_answer(answer, EVIDENCE)["failed_checks"])

    def test_invalid_structure_fails(self):
        self.assertIn("valid_structure", validate_comparison_answer({"answer": 42}, EVIDENCE)["failed_checks"])


if __name__ == "__main__":
    unittest.main()
