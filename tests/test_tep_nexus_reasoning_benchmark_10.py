"""Offline checks for ten-level benchmark definitions and format handling."""

# Created: 2026-11-02
# Author: Harish
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_reasoning_benchmark_10 import QUESTIONS, limited_checks, evidence_for_level

class TestBenchmark10(unittest.TestCase):
    def test_exactly_ten_distinct_levels(self):
        self.assertEqual(len(QUESTIONS), 10)
        self.assertEqual(len(set(name for name, _ in QUESTIONS)), 10)
        self.assertTrue(all(question.strip() for _, question in QUESTIONS))

    def test_format_only_not_factual_score(self):
        result = limited_checks(1, {"answer": "anything", "evidence_used": [],
                                   "limitations": []}, {})
        self.assertEqual(result["status"], "BASIC_FORMAT_PASSED")
        self.assertTrue(result["manual_review_required"])

    def test_malformed_types_do_not_crash(self):
        result = limited_checks(1, {"answer": None, "evidence_used": [],
                                   "limitations": []}, {})
        self.assertEqual(result["status"], "BASIC_FORMAT_FAILED")

    def test_missing_schema(self):
        self.assertEqual(limited_checks(1, {"answer": "x"}, {})["status"], "SCHEMA_FAILED")

    def test_evidence_scoping(self):
        e = {"mappings": [1], "comparison": {"series": []}, "run_id": "r",
             "shared_run_provenance": "NOT_VERIFIED"}
        self.assertEqual(set(evidence_for_level(1, e)), {"mappings"})
        self.assertEqual(set(evidence_for_level(2, e)), {"comparison", "run_id"})
        self.assertEqual(evidence_for_level(10, e), e)

if __name__ == "__main__":
    unittest.main()
