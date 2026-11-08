"""Offline tests for TimescaleDB coverage classification."""

# Created: 2026-11-02
# Author: Harish
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_temporal_coverage import build_coverage

DISCOVERY = {"candidates": [
    {"engineering_function": "FI_101", "status": "UNIQUE_PROVISIONAL_CANDIDATE",
     "mappings": [{"operational_signal": "XMEAS1"}]},
    {"engineering_function": "TI_101", "status": "UNIQUE_PROVISIONAL_CANDIDATE",
     "mappings": [{"operational_signal": "XMEAS9"}]},
]}


class TestTemporalCoverage(unittest.TestCase):
    def test_one_signal_with_samples(self):
        result = build_coverage(DISCOVERY, [("XMEAS9", 201, 0.5)])
        self.assertEqual(result["functions_with_samples"], 1)
        self.assertEqual(result["functions_without_samples"], 1)
        self.assertEqual(result["functions"][1]["signals"][0]["latest_simulation_seconds"], 1800.0)

    def test_no_rows(self):
        self.assertEqual(build_coverage(DISCOVERY, [])["functions_without_samples"], 2)

    def test_ambiguous_mapping(self):
        d = {"candidates": [{"engineering_function": "FI_101",
             "status": "AMBIGUOUS_REVIEW_REQUIRED",
             "mappings": [{"operational_signal": "X1"}, {"operational_signal": "X2"}]}]}
        self.assertEqual(build_coverage(d, [("X1", 10, 1)])["ambiguous_functions"], 1)

    def test_count_preserved(self):
        result = build_coverage(DISCOVERY, [("XMEAS1", 33, 1.0)])
        self.assertEqual(result["functions"][0]["signals"][0]["sample_count"], 33)


if __name__ == "__main__":
    unittest.main()
