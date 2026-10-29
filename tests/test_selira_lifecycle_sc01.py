"""Regression tests for the SC-01 lifecycle reference engine."""
import tempfile
import unittest
from pathlib import Path
from selira_integration.lifecycle import Snapshot, Lifecycle, detect, impacted

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.r1 = Snapshot("R1", {"A": "X", "B": "Y"}, {"P": "X", "Q": "Y"})

    def test_identifier_change_invalidates_only_dependent_asset(self):
        r2 = Snapshot("R2", self.r1.assigned, {"P": "Z", "Q": "Y"})
        engine = Lifecycle()
        engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], ["A"])
        self.assertEqual(result["current"], {"A": "INVALID", "B": "VALIDATED"})
        self.assertTrue(result["baseline_agreement"])
        self.assertTrue(result["unaffected_unchanged"])
        self.assertEqual(result["selective_evaluations"], 1)
        self.assertEqual(result["full_evaluations"], 2)

    def test_restore_and_history(self):
        r2 = Snapshot("R2", self.r1.assigned, {"P": "Z", "Q": "Y"})
        with tempfile.TemporaryDirectory() as d:
            history = Path(d) / "audit.jsonl"
            engine = Lifecycle(history)
            engine.initialize(self.r1)
            engine.apply(self.r1, r2)
            result = engine.apply(r2, self.r1)
            self.assertEqual(result["current"]["A"], "VALIDATED")
            lines = history.read_text().splitlines()
            self.assertEqual(len(lines), 6)
            self.assertIn('"previous_outcome": "INVALID"', lines[-1])

    def test_duplicate_catalog_identifier(self):
        r2 = Snapshot("R2", self.r1.assigned, {"P": "X", "Q": "Y", "R": "X"})
        engine = Lifecycle(); engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], ["A"])
        self.assertEqual(result["current"]["A"], "INVALID")
        self.assertTrue(result["baseline_agreement"])

    def test_unrelated_catalog_change_no_revalidation(self):
        r2 = Snapshot("R2", self.r1.assigned, {"P": "X", "Q": "Y", "R": "unused"})
        engine = Lifecycle(); engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], [])
        self.assertEqual(result["selective_evaluations"], 0)

    def test_asset_reference_change(self):
        r2 = Snapshot("R2", {"A": "missing", "B": "Y"}, self.r1.catalog)
        engine = Lifecycle(); engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], ["A"])
        self.assertEqual(result["current"]["A"], "INVALID")

    def test_incomplete_catalog_revalidates_everything(self):
        r2 = Snapshot("R2", self.r1.assigned, self.r1.catalog, complete=False)
        engine = Lifecycle(); engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], ["A", "B"])
        self.assertEqual(result["current"]["A"], "INDETERMINATE")
        self.assertTrue(result["baseline_agreement"])

    def test_removal_of_assigned_reference(self):
        r2 = Snapshot("R2", {"B": "Y"}, self.r1.catalog)
        engine = Lifecycle(); engine.initialize(self.r1)
        result = engine.apply(self.r1, r2)
        self.assertEqual(result["affected"], ["A"])
        self.assertNotIn("A", result["current"])
        self.assertTrue(result["baseline_agreement"])

if __name__ == "__main__":
    unittest.main()
