"""Created: 2026-10-30
Author: Harish"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_selira_e1_e10_benchmark import evaluate, synthetic_case, summarize


class EvidenceBenchmarkTests(unittest.TestCase):
    def test_source_labels_are_evaluated_not_overridden(self):
        expected = {"E1":"V","E2":"U","E3":"F","E4":"F",
                    "E5":"U","E6":"F","E7":"U","E8":"V","E9":"V"}
        for name, status in expected.items():
            with self.subTest(name=name):
                case = evaluate(name)
                self.assertEqual(case["sourceStatus"], status)
                self.assertEqual(case["referenceSourceStatus"], status)
                self.assertFalse(case["decision"]["authorization"])

    def test_task_specific_failures(self):
        coverage = evaluate("E8")
        self.assertEqual(coverage["decision"]["consumers"]["CAC-01"]["decision"], "F")
        self.assertEqual(coverage["decision"]["consumers"]["CAC-02"]["decision"], "V")
        approval = evaluate("E9")
        self.assertEqual(approval["decision"]["consumers"]["CAC-01"]["decision"], "V")
        self.assertEqual(approval["decision"]["consumers"]["CAC-02"]["decision"], "U")

    def test_evidence_mutations_not_status_overrides(self):
        sc, cac = synthetic_case("E3")
        self.assertEqual(sc[1]["quantityAssertions"][1]["quantityKind"], "temperature")
        self.assertEqual(sc[2]["unitAssertions"][1]["unit"], "kPa")
        sc, cac = synthetic_case("E5")
        self.assertNotEqual(sc[3]["task"]["revision"],
                            sc[3]["applicabilityAssertions"][0]["revision"])

    def test_naive_comparators_are_labeled(self):
        result = evaluate("E3")
        self.assertEqual(result["comparators"]["B1_identifier_presence"], "ACCEPT")
        self.assertEqual(result["comparators"]["B2_structural_presence"], "ACCEPT")
        self.assertEqual(result["sourceStatus"], "F")

    def test_summary(self):
        cases = [evaluate("E" + str(n)) for n in range(1,10)]
        metrics = summarize(cases)
        self.assertEqual(metrics["sourceReferenceAgreement"], 9)
        self.assertEqual(metrics["unsupportedAcceptanceDenominator"], 6)
        self.assertEqual(metrics["seliraUnjustifiedSourceV"], 0)
        self.assertEqual(metrics["authorizationTrueCount"], 0)


if __name__ == "__main__":
    unittest.main()
