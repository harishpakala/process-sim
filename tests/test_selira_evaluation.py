"""Deterministic comparison tests; no live infrastructure required."""
import unittest

from process_sim.selira.evaluation import evaluate, scenarios


class ComparisonTests(unittest.TestCase):
    def test_scenario_count(self):
        self.assertEqual(len(scenarios()), 18)

    def test_no_unsafe_acceptance_for_fixture(self):
        self.assertEqual(evaluate()["selira"]["unsafe_accept"], 0)

    def test_baseline_has_unsafe_acceptance(self):
        self.assertGreater(evaluate()["legacy"]["unsafe_accept"], 0)

    def test_rejected_alternative_avoids_false_withholding(self):
        rows = evaluate()["scenarios"]
        for row in rows:
            if row["scenario"].endswith(":rejected_competitor"):
                self.assertEqual(row["selira"], row["oracle"])

    def test_metrics_partition_scenarios(self):
        result = evaluate()
        for policy in ("legacy", "selira"):
            self.assertEqual(sum(result[policy].values()), 18)


if __name__ == "__main__":
    unittest.main()
