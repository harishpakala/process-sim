import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from process_sim.selira.sc05_contract import evaluate_sc05, assess_graphdb_sc05
from process_sim.selira.cac_contracts import evaluate_cac
from process_sim.selira.integrated_contracts import conjunction, aggregate
from scripts.run_selira_integrated_experiment import sc05_fixture, cac_fixture, run_scenario


class IntegratedContractsTests(unittest.TestCase):
    def test_sc05_synthetic_v(self):
        r = evaluate_sc05(sc05_fixture())
        self.assertEqual(r["status"], "V")
        self.assertFalse(r["authorization"])

    def test_sc05_synthetic_f(self):
        self.assertEqual(evaluate_sc05(sc05_fixture(True))["status"], "F")

    def test_sc05_real_discovery_unknown_with_provenance(self):
        report = {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY", "truncated": False,
                  "facts": [{"s": "urn:mapping", "p": "https://example.org/hasMappingStatus",
                             "o": "PROVISIONAL_ENGINEERING_MATCH", "g": "urn:graph"}]}
        r = assess_graphdb_sc05(report)
        self.assertEqual(r["status"], "U")
        self.assertEqual(r["evidence"][0]["graph"], "urn:graph")

    def test_cac_four_valued_controls(self):
        for contract in ("CAC-01", "CAC-02"):
            for mode in ("V", "F", "U", "NA"):
                with self.subTest(contract=contract, mode=mode):
                    r = evaluate_cac(contract, cac_fixture(contract, mode), "V")
                    self.assertEqual(r["status"], mode)
                    self.assertFalse(r["authorization"])

    def test_cac_verified_fitness_does_not_override_unknown_source(self):
        r = evaluate_cac("CAC-01", cac_fixture("CAC-01"), "U")
        self.assertEqual(r["status"], "V")
        self.assertFalse(r["consumerAcceptance"])

    def test_aggregate(self):
        self.assertEqual(conjunction(["V"] * 5), "V")
        self.assertEqual(conjunction(["V", "U", "V"]), "U")
        self.assertEqual(conjunction(["V", "F", "U"]), "F")
        self.assertEqual(conjunction([]), "U")

    def test_synthetic_verified_integrated(self):
        r = run_scenario("synthetic-verified")
        self.assertEqual(r["decision"]["sourceQualification"], "V")
        self.assertTrue(all(x["status"] == "V" for x in r["contracts"]))
        self.assertFalse(r["decision"]["authorization"])
        self.assertFalse(r["decision"]["consumers"]["CAC-01"]["accepted"])

    def test_synthetic_contradiction_integrated(self):
        r = run_scenario("F")
        self.assertEqual(r["decision"]["sourceQualification"], "F")
        self.assertTrue(all(x["status"] == "F" for x in r["contracts"]))

    def test_missing_contract_fails_closed(self):
        with self.assertRaises(ValueError):
            aggregate([{"contract": "SC-01", "status": "V"}])


if __name__ == "__main__":
    unittest.main()
