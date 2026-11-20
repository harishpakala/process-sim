"""Offline regression checks for existing single-domain operation routing."""
import unittest

from process_sim.dtwise.experimental_shacl_query_classifier import _structural_classification
from run_shacl_planner import CASES


class SingleDomainClassificationTests(unittest.TestCase):
    def test_existing_cases_keep_their_operations(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                result = _structural_classification(case["question"])
                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "supported")
                self.assertEqual(result["operation"], case["mode"].removeprefix("--"))

    def test_aggregation_is_unsupported(self):
        result = _structural_classification("Count devices in ECAD")
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["operation"])


if __name__ == "__main__":
    unittest.main()
