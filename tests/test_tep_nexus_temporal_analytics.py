"""Offline deterministic temporal analytics regression tests."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_temporal_analytics import summarize_history


def samples(values, seconds=None):
    seconds = seconds if seconds is not None else [i * 60 for i in range(len(values))]
    return [{"simulation_seconds": t, "value": y} for t, y in zip(seconds, values)]


class TestTemporalAnalytics(unittest.TestCase):
    def test_linear_increase(self):
        result = summarize_history(samples([1, 3, 5]))
        self.assertAlmostEqual(result["linear_regression_slope_per_simulation_minute"], 2)
        self.assertAlmostEqual(result["endpoint_change"], 4)
        self.assertAlmostEqual(result["mean"], 3)
        self.assertAlmostEqual(result["standard_deviation_population"], math.sqrt(8 / 3))

    def test_linear_decrease(self):
        result = summarize_history(samples([5, 3, 1]))
        self.assertAlmostEqual(result["linear_regression_slope_per_simulation_minute"], -2)

    def test_constant(self):
        result = summarize_history(samples([4, 4, 4]))
        self.assertEqual(result["linear_regression_slope_per_simulation_minute"], 0)
        self.assertEqual(result["standard_deviation_population"], 0)

    def test_irregular_spacing(self):
        result = summarize_history(samples([0, 2, 6], [0, 60, 180]))
        self.assertAlmostEqual(result["linear_regression_slope_per_simulation_minute"], 2)

    def test_empty(self):
        self.assertEqual(summarize_history([])["status"], "INSUFFICIENT_DATA")

    def test_single(self):
        self.assertEqual(summarize_history(samples([4]))["status"], "INSUFFICIENT_DATA")

    def test_repeated_timestamp(self):
        with self.assertRaises(ValueError):
            summarize_history(samples([1, 2], [0, 0]))

    def test_reverse_timestamp(self):
        with self.assertRaises(ValueError):
            summarize_history(samples([1, 2], [60, 0]))

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            summarize_history(samples([1, float("nan")]))

    def test_truncation_flag(self):
        self.assertTrue(summarize_history(samples([1, 2]), truncated=True)["history_truncated_by_limit"])


if __name__ == "__main__":
    unittest.main()
