"""Offline tests for evidence-derived full-coverage benchmark fixtures."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_expand_benchmark import expand_fixtures


class TestExpandBenchmark(unittest.TestCase):
    def setUp(self):
        self.baseline = [
            {"id": "fi", "function": "FI_101", "question": "FI", "expected": "complete"},
            {"id": "unsupported", "function": "FI_999", "question": "invalid",
             "expected": "reject", "expected_error": "Unsupported engineering function"},
        ]

    def test_adds_only_uncovered_supported_functions(self):
        expanded = expand_fixtures(self.baseline, {"FI_101": {}, "LI_102": {}})
        self.assertEqual(len(expanded), 3)
        self.assertEqual(expanded[-1]["function"], "LI_102")
        self.assertEqual(expanded[-1]["expected"], "complete")
        self.assertIn("LI_102", expanded[-1]["question"])
        self.assertEqual(expanded[:2], self.baseline)

    def test_deterministic_order(self):
        supported = {"PI_102": {}, "FI_101": {}, "LI_102": {}}
        expanded = expand_fixtures(self.baseline, supported)
        self.assertEqual([x["function"] for x in expanded[2:]], ["LI_102", "PI_102"])

    def test_rejects_missing_baseline_support(self):
        with self.assertRaisesRegex(ValueError, "missing from registry"):
            expand_fixtures(self.baseline, {"LI_102": {}})

    def test_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            expand_fixtures(self.baseline + [dict(self.baseline[0])], {"FI_101": {}})


if __name__ == "__main__":
    unittest.main()
