"""Offline unit tests for the Step 5 benchmark classifier."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_benchmark import evaluate_case

CASE = {"id": "fi", "function": "FI_101", "expected": "complete"}
class TestBenchmark(unittest.TestCase):
    def test_valid_completion(self):
        report = {"status": "COMPLETED", "validated_plan": {"engineering_function": "FI_101"},
                  "answer_validation": "CHECKS_PASSED_LIMITED_SCOPE",
                  "answer_validation_details": {"failed_checks": []}}
        self.assertTrue(evaluate_case(CASE, report, 0)[0])
    def test_wrong_function(self):
        report = {"status": "COMPLETED", "validated_plan": {"engineering_function": "VC_101"},
                  "answer_validation": "CHECKS_PASSED_LIMITED_SCOPE",
                  "answer_validation_details": {"failed_checks": []}}
        self.assertFalse(evaluate_case(CASE, report, 0)[0])
    def test_rejection_requires_no_evidence(self):
        case = dict(CASE, expected="reject")
        self.assertTrue(evaluate_case(case, {"status": "ERROR", "evidence": None}, 1)[0])
        self.assertFalse(evaluate_case(case, {"status": "ERROR", "evidence": {"x": 1}}, 1)[0])
    def test_rejection_cannot_be_success(self):
        self.assertFalse(evaluate_case(dict(CASE, expected="reject"), {"status": "COMPLETED"}, 0)[0])
    def test_wrong_rejection_reason(self):
        case = dict(CASE, expected="reject",
                    expected_error="Planned engineering function does not match")
        self.assertFalse(evaluate_case(case, {
            "status": "ERROR", "evidence": None,
            "error": "ConnectionError: service unavailable"}, 1)[0])
        self.assertTrue(evaluate_case(case, {
            "status": "ERROR", "evidence": None,
            "error": "ValueError: Planned engineering function does not match the explicit identifier"}, 1)[0])
    def test_rejection_with_evidence_fails_even_with_matching_reason(self):
        case = dict(CASE, expected="reject", expected_error="Unsupported engineering function")
        self.assertFalse(evaluate_case(case, {
            "status": "ERROR", "evidence": {"latest": 1},
            "error": "ValueError: Unsupported engineering function"}, 1)[0])

if __name__ == "__main__":
    unittest.main()
