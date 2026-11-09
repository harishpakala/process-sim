"""Created: 2026-10-30
Author: Harish"""

import unittest
from process_sim.selira.sc01_contract import evaluate_sc01
from scripts.run_selira_sc01_experiment import synthetic_case, graphdb_case


class SC01Tests(unittest.TestCase):
    def test_synthetic_verified(self):
        result = evaluate_sc01(synthetic_case())
        self.assertEqual(result["status"], "V")
        self.assertFalse(result["authorization"])

    def test_synthetic_contradiction(self):
        result = evaluate_sc01(synthetic_case("CONTRADICTED"))
        self.assertEqual(result["status"], "F")
        self.assertFalse(result["authorization"])

    def test_graphdb_discovery_unknown(self):
        case = graphdb_case({"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                             "facts": [{}], "truncated": False})
        result = evaluate_sc01(case)
        self.assertEqual(result["status"], "U")
        self.assertFalse(result["authorization"])

    def test_untrusted_assertions_unknown(self):
        case = synthetic_case()
        case["assertions"][0]["authority"] = "UNVERIFIED"
        self.assertEqual(evaluate_sc01(case)["status"], "U")

    def test_missing_revision_unknown(self):
        case = synthetic_case()
        case.pop("revision")
        self.assertEqual(evaluate_sc01(case)["status"], "U")


if __name__ == "__main__":
    unittest.main()
