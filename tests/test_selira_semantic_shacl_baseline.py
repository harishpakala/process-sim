"""Regression tests for engineering-aware SHACL-SPARQL comparison."""
import sys
import unittest
from pathlib import Path
from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_selira_semantic_shacl_baseline import SHAPES, SEMANTIC, run_case


class SemanticSHACLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.structural = Graph().parse(SHAPES, format="turtle")
        cls.semantic = Graph().parse(SEMANTIC, format="turtle")

    def compare(self, case_id):
        return run_case(case_id, self.structural, self.semantic)

    def test_verified_fixture_conforms(self):
        row = self.compare("E1")
        self.assertTrue(row["structuralSHACL"]["conforms"])
        self.assertTrue(row["semanticSHACL"]["conforms"])
        self.assertEqual(row["seliraSource"], "V")

    def test_semantic_contradictions_detected(self):
        for case_id in ("E3", "E4", "E6"):
            with self.subTest(case=case_id):
                row = self.compare(case_id)
                self.assertTrue(row["structuralSHACL"]["conforms"])
                self.assertFalse(row["semanticSHACL"]["conforms"])
                self.assertEqual(row["seliraSource"], "F")

    def test_revision_mismatch_detected_without_claiming_source_failure(self):
        row = self.compare("E5")
        self.assertTrue(row["structuralSHACL"]["conforms"])
        self.assertFalse(row["semanticSHACL"]["conforms"])
        self.assertEqual(row["seliraSource"], "U")

    def test_consumer_violation_is_not_source_failure(self):
        row = self.compare("E8")
        self.assertTrue(row["structuralSHACL"]["conforms"])
        self.assertFalse(row["semanticSHACL"]["conforms"])
        self.assertEqual(row["seliraSource"], "V")
        self.assertEqual(row["seliraCAC01"], "F")
        self.assertFalse(row["engineeringAuthorization"])

    def test_missing_assertions_still_nonconform(self):
        for case_id in ("E2", "E7", "E9"):
            with self.subTest(case=case_id):
                self.assertFalse(self.compare(case_id)["semanticSHACL"]["conforms"])


if __name__ == "__main__":
    unittest.main()
