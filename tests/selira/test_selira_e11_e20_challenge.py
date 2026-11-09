"""Regression checks for exploratory E11-E20 challenge protocol."""

# Created: 2026-10-30
# Author: Harish
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_selira_e11_e20_challenge import CHALLENGES, build, scenario


class ChallengeTests(unittest.TestCase):
    def test_ten_scenarios_defined(self):
        self.assertEqual(list(CHALLENGES),
                         ["E" + str(i) for i in range(11, 21)])

    def test_unsupported_cases_are_not_scored(self):
        for case in ("E19", "E20"):
            _, _, supported = scenario(case)
            self.assertFalse(supported)

    def test_source_fixtures_are_independent(self):
        a, _, _ = scenario("E11")
        b, _, _ = scenario("E14")
        self.assertEqual(len(a[0]["assertions"]), 5)
        self.assertEqual(len(b[0]["assertions"]), 2)

    def test_run_preserves_limitations_and_no_reference_labels(self):
        result = build()
        self.assertEqual(len(result["cases"]), 10)
        self.assertEqual(result["summary"]["executed"], 8)
        self.assertEqual(result["summary"]["unsupported"], 2)
        for case in result["cases"]:
            self.assertFalse(case["engineeringAuthorization"])
            if case["evaluation"] == "EXECUTED_EXPLORATORY":
                self.assertIsNone(case["referenceLabels"])
            else:
                self.assertNotIn("sourceStatus", case)


if __name__ == "__main__":
    unittest.main()
