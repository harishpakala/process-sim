"""Task-aware SHACL regression checks and blind-review schema."""

# Created: 2026-10-30
# Author: Harish
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_selira_task_aware_comparison import (
    TASK_SHAPES, task_validation, export_review_template)


class TaskAwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = Graph().parse(TASK_SHAPES, format="turtle")

    def test_e1_both_consumers_conform(self):
        outcomes = task_validation("E1", self.shapes)
        self.assertTrue(outcomes["CAC-01"]["conforms"])
        self.assertTrue(outcomes["CAC-02"]["conforms"])

    def test_e8_only_cac01_fails(self):
        outcomes = task_validation("E8", self.shapes)
        self.assertFalse(outcomes["CAC-01"]["conforms"])
        self.assertTrue(outcomes["CAC-02"]["conforms"])

    def test_e9_only_cac02_fails(self):
        outcomes = task_validation("E9", self.shapes)
        self.assertTrue(outcomes["CAC-01"]["conforms"])
        self.assertFalse(outcomes["CAC-02"]["conforms"])

    def test_blind_template_contains_no_reference_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reviews.csv"
            export_review_template(path)
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 30)
        self.assertEqual({row["referenceStatus"] for row in rows}, {""})
        self.assertEqual({row["task"] for row in rows},
                         {"SOURCE", "CAC-01", "CAC-02"})


if __name__ == "__main__":
    unittest.main()
