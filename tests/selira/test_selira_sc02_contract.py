"""Created: 2026-10-30
Author: Harish"""

import unittest
from process_sim.selira.sc02_contract import evaluate_sc02, assess_graphdb_sc02
from scripts.run_selira_sc02_experiment import synthetic_case


class SC02Tests(unittest.TestCase):
    def test_verified_synthetic(self):
        result = evaluate_sc02(synthetic_case())
        self.assertEqual(result["status"], "V")
        self.assertFalse(result["authorization"])

    def test_mismatch_synthetic(self):
        self.assertEqual(evaluate_sc02(synthetic_case("temperature"))["status"], "F")

    def test_untrusted_assertion_unknown(self):
        case = synthetic_case()
        case["quantityAssertions"][0]["authority"] = "UNVERIFIED"
        self.assertEqual(evaluate_sc02(case)["status"], "U")

    def test_conflicting_authenticated_claims(self):
        case = synthetic_case()
        record = dict(case["quantityAssertions"][0])
        record["quantityKind"] = "temperature"
        case["quantityAssertions"].append(record)
        self.assertEqual(evaluate_sc02(case)["status"], "F")

    def test_graphdb_observation_unknown(self):
        row = {"s": "urn:measurement", "p": "https://example.org/dexpi/hasMeasuredVariable",
               "o": "", "g": "urn:dexpi"}
        report = {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                  "facts": [row], "truncated": False}
        result = assess_graphdb_sc02(report)
        self.assertEqual(result["status"], "U")
        self.assertEqual(result["evidence"][0]["graph"], "urn:dexpi")


if __name__ == "__main__":
    unittest.main()
