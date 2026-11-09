"""Regression tests for the actual pySHACL structural comparator.

Install optional baseline dependencies before running these tests.
"""

# Created: 2026-10-30
# Author: Harish
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rdflib import Graph
from run_selira_shacl_baseline import SHAPES, make_graph, run_case


class SHACLComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = Graph().parse(SHAPES, format="turtle")

    def test_e1_conforms(self):
        result = run_case("E1", self.shapes)
        self.assertTrue(result["shaclConforms"])
        self.assertEqual(result["seliraSource"], "V")

    def test_missing_link_and_binding_fail_structural_shape(self):
        for case in ("E2", "E7"):
            with self.subTest(case=case):
                result = run_case(case, self.shapes)
                self.assertFalse(result["shaclConforms"])
                self.assertEqual(result["seliraSource"], "U")

    def test_present_but_contradictory_evidence_passes_structural_shape(self):
        for case in ("E3", "E4", "E6"):
            with self.subTest(case=case):
                result = run_case(case, self.shapes)
                self.assertTrue(result["shaclConforms"])
                self.assertEqual(result["seliraSource"], "F")

    def test_revision_mismatch_is_not_missing_structure(self):
        result = run_case("E5", self.shapes)
        self.assertTrue(result["shaclConforms"])
        self.assertEqual(result["seliraSource"], "U")

    def test_missing_consumer_approval_check_fails_shape(self):
        result = run_case("E9", self.shapes)
        self.assertFalse(result["shaclConforms"])
        self.assertEqual(result["seliraCAC02"], "U")

    def test_no_derived_verdict_in_graph(self):
        graph = make_graph("E3")
        self.assertNotIn("sourceQualification", graph.serialize(format="turtle"))


if __name__ == "__main__":
    unittest.main()
