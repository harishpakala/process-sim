"""Offline tests for the TEP NEXUS constrained query planner."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tep_nexus_ollama_query_planner import validate_plan


class TestTEPNexusQueryPlanner(unittest.TestCase):

    def make_plan(self, **changes):
        plan = {
            "intent": "latest_and_history",
            "engineering_function": "TI_101",
            "history_window_minutes": 10,
            "include_asset": True,
            "include_provenance": True,
        }
        plan.update(changes)
        return plan

    def test_valid_plan(self):
        question = (
            "For TI_101, show the latest measurement "
            "over the last 10 simulation minutes."
        )
        result = validate_plan(self.make_plan(), question)
        self.assertEqual(result["engineering_function"], "TI_101")
        self.assertEqual(result["history_window_minutes"], 10.0)

    def test_unsupported_function(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(engineering_function="TI_999"),
                "Show TI_999 measurements."
            )

    def test_function_mismatch(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(),
                "Show TI_102 measurements."
            )

    def test_missing_function_in_question(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(),
                "Show the latest measurement."
            )

    def test_excessive_history_window(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(history_window_minutes=180),
                "Show TI_101 over the last 180 minutes."
            )

    def test_explicit_window_mismatch(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(history_window_minutes=10),
                "Show TI_101 over the last 30 minutes."
            )

    def test_hour_conversion(self):
        result = validate_plan(
            self.make_plan(history_window_minutes=60),
            "Show TI_101 over the last 1 simulation hour."
        )
        self.assertEqual(result["history_window_minutes"], 60.0)

    def test_unknown_intent(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(intent="execute_sql"),
                "Show TI_101 measurements."
            )

    def test_extra_plan_field(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(sql="DELETE FROM signal_samples"),
                "Show TI_101 measurements."
            )

    def test_boolean_history_window_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(history_window_minutes=True),
                "Show TI_101 measurements."
            )

    def test_invalid_asset_flag(self):
        with self.assertRaises(ValueError):
            validate_plan(
                self.make_plan(include_asset="yes"),
                "Show TI_101 measurements."
            )

    def test_provenance_is_preserved(self):
        result = validate_plan(
            self.make_plan(include_provenance=False),
            "Show TI_101 measurements."
        )
        self.assertTrue(result["include_provenance"])


if __name__ == "__main__":
    unittest.main()
