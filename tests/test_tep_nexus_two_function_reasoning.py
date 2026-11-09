"""Offline tests for the two-function reasoning prototype."""

# Created: 2026-11-02
# Author: Harish
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_two_function_reasoning import validate_comparison_plan, compare_series


class TestTwoFunctionReasoning(unittest.TestCase):
    def setUp(self):
        self.registry = {"FI_101": {}, "PI_101": {}}
        self.question = "Compare FI_101 and PI_101 over the last 10 simulation minutes"
        self.plan = {"engineering_functions": ["FI_101", "PI_101"], "history_window_minutes": 10}

    def test_valid_plan(self):
        self.assertEqual(validate_comparison_plan(self.plan, self.question, self.registry), self.plan)

    def test_rejects_function_substitution(self):
        plan = dict(self.plan, engineering_functions=["FI_101", "FI_102"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_comparison_plan(plan, self.question, self.registry)

    def test_rejects_duplicate_function(self):
        plan = dict(self.plan, engineering_functions=["FI_101", "FI_101"])
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_comparison_plan(plan, self.question, self.registry)

    def test_rejects_changed_window(self):
        plan = dict(self.plan, history_window_minutes=5)
        with self.assertRaisesRegex(ValueError, "changed"):
            validate_comparison_plan(plan, self.question, self.registry)

    def test_rejects_nan_window(self):
        plan = dict(self.plan, history_window_minutes=float("nan"))
        with self.assertRaises(ValueError):
            validate_comparison_plan(plan, self.question, self.registry)

    @staticmethod
    def series(signal, points, truncated=False):
        return {"status": "AVAILABLE", "signal": signal,
                "history": {"truncated_by_limit": truncated,
                            "samples": [{"simulation_seconds": t, "value": v} for t, v in points]}}

    def test_exact_alignment_and_relative_change(self):
        a = self.series("XMEAS1", [(0, 10), (60, 12), (120, 15)])
        b = self.series("XMEAS2", [(0, 20), (60, 21), (120, 22)])
        result = compare_series([a, b])
        self.assertEqual(result["common_sample_count"], 3)
        self.assertEqual(result["larger_absolute_relative_change_index"], 0)
        self.assertAlmostEqual(result["series"][0]["relative_endpoint_change_percent"], 50)
        self.assertAlmostEqual(result["series"][1]["relative_endpoint_change_percent"], 10)

    def test_rejects_no_common_window(self):
        a = self.series("A", [(0, 1), (60, 2)])
        b = self.series("B", [(120, 1), (180, 2)])
        with self.assertRaisesRegex(ValueError, "common"):
            compare_series([a, b])

    def test_rejects_truncation(self):
        a = self.series("A", [(0, 1), (60, 2)], True)
        b = self.series("B", [(0, 1), (60, 2)])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            compare_series([a, b])

    def test_zero_baseline_does_not_invent_percentage(self):
        a = self.series("A", [(0, 0), (60, 2)])
        b = self.series("B", [(0, 1), (60, 2)])
        result = compare_series([a, b])
        self.assertFalse(result["comparison_available"])
        self.assertIsNone(result["larger_absolute_relative_change_index"])


if __name__ == "__main__":
    unittest.main()
