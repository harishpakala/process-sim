"""Created: 2026-10-30
Author: Harish"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_selira_mixed_experiment import build_report


class MixedVerdictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report()
        cls.cases = {r["scenario"]: r for r in cls.report["scenarios"]}

    def test_one_unknown(self):
        r = self.cases["one-unknown"]["decision"]
        self.assertEqual(r["sourceQualification"], "U")
        self.assertEqual(r["consumers"]["CAC-01"]["decision"], "U")

    def test_failure_dominates_unknown(self):
        r = self.cases["one-failure-and-one-unknown"]["decision"]
        self.assertEqual(r["sourceQualification"], "F")
        self.assertEqual(r["consumers"]["CAC-02"]["decision"], "F")

    def test_consumer_violation_independent(self):
        r = self.cases["consumer-violation-source-verified"]["decision"]
        self.assertEqual(r["sourceQualification"], "V")
        self.assertEqual(r["consumers"]["CAC-01"]["decision"], "F")
        self.assertEqual(r["consumers"]["CAC-02"]["decision"], "V")

    def test_out_of_scope(self):
        r = self.cases["consumer-not-applicable-source-verified"]["decision"]
        self.assertEqual(r["consumers"]["CAC-02"]["decision"], "NA")
        self.assertFalse(r["consumers"]["CAC-02"]["accepted"])

    def test_unknown_source_blocks_verified_consumer(self):
        r = self.cases["source-unknown-consumer-fitness-verified"]["decision"]
        self.assertEqual(r["sourceQualification"], "U")
        self.assertEqual(r["consumers"]["CAC-01"]["decision"], "U")

    def test_cac_task_controls(self):
        for name, controls in self.report["taskSpecificControls"].items():
            with self.subTest(contract=name):
                self.assertEqual(controls["verifiedTaskFixture"]["status"], "V")
                self.assertEqual(controls["violatedTaskFixture"]["status"], "F")
                self.assertEqual(controls["incompleteTaskFixture"]["status"], "U")
                self.assertEqual(controls["outsideScope"]["status"], "NA")
                self.assertFalse(controls["verifiedFitnessUnknownSource"]["consumerAcceptance"])

    def test_all_scenarios_fail_closed(self):
        for r in self.report["scenarios"]:
            with self.subTest(scenario=r["scenario"]):
                self.assertFalse(r["decision"]["authorization"])
                self.assertTrue(all(not v["accepted"] for v in r["decision"]["consumers"].values()))

    def test_numbering_not_claimed_reconciled(self):
        self.assertEqual(self.report["contractIdentity"]["alignment"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
