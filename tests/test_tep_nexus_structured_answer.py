"""Offline tests for structured comparison evidence validation."""

# Created: 2026-11-02
# Author: Harish
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_structured_answer import validate_structured_answer

EVIDENCE = {"comparison": {
    "common_start_simulation_seconds": 2916.0,
    "common_end_simulation_seconds": 3514.0,
    "common_sample_count": 201,
    "larger_absolute_relative_change_index": 0,
    "series": [
        {"engineering_function": "FI_101", "endpoint_change": -0.000503544571995751,
         "relative_endpoint_change_percent": -0.20088058804540695},
        {"engineering_function": "PI_101", "endpoint_change": 0.27829719819646925,
         "relative_endpoint_change_percent": 0.010290357685705524},
    ],
}}
ANSWER = {
    "engineering_functions": ["FI_101", "PI_101"],
    "simulation_interval_seconds": [2916, 3514],
    "aligned_sample_count": 201,
    "measurements": [
        {"engineering_function": "FI_101", "endpoint_change": -0.000503544571995751,
         "relative_endpoint_change_percent": -0.20088058804540695},
        {"engineering_function": "PI_101", "endpoint_change": 0.27829719819646925,
         "relative_endpoint_change_percent": 0.010290357685705524},
    ],
    "larger_absolute_relative_change_function": "FI_101",
    "conclusion": "FI_101 changed more relative to its initial value than PI_101.",
    "limitations": ["Provisional engineering mapping.", "Physical sensor binding not verified.",
                    "Shared run provenance not verified.", "Causal inference not supported."],
}

class TestStructuredAnswer(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(validate_structured_answer(ANSWER, EVIDENCE)["failed_checks"], [])

    def test_wrong_winner(self):
        a = dict(ANSWER, larger_absolute_relative_change_function="PI_101")
        failures = validate_structured_answer(a, EVIDENCE)["failed_checks"]
        self.assertIn("winner", failures)
        self.assertIn("conclusion_consistent_with_evidence", failures)

    def test_wrong_winner_and_matching_wrong_conclusion(self):
        a = dict(ANSWER, larger_absolute_relative_change_function="PI_101",
                 conclusion="PI_101 changed more than FI_101.")
        failures = validate_structured_answer(a, EVIDENCE)["failed_checks"]
        self.assertIn("winner", failures)
        self.assertIn("conclusion_consistent_with_evidence", failures)

    def test_wrong_number(self):
        a = dict(ANSWER, measurements=[dict(ANSWER["measurements"][0], endpoint_change=42),
                                        ANSWER["measurements"][1]])
        self.assertIn("measurements", validate_structured_answer(a, EVIDENCE)["failed_checks"])

    def test_missing_provenance(self):
        a = dict(ANSWER, limitations=["Provisional mapping", "Physical sensor not verified",
                                      "Causal inference not supported"])
        self.assertIn("limitations", validate_structured_answer(a, EVIDENCE)["failed_checks"])

    def test_missing_field(self):
        a = dict(ANSWER)
        del a["measurements"]
        self.assertIn("schema", validate_structured_answer(a, EVIDENCE)["failed_checks"])

if __name__ == "__main__":
    unittest.main()
