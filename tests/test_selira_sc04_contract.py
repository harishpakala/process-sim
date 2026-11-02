import unittest
from process_sim.selira.sc04_contract import evaluate_sc04, assess_graphdb_sc04
from scripts.run_selira_sc04_experiment import synthetic_case


class SC04Tests(unittest.TestCase):
    def test_applicable(self):
        result = evaluate_sc04(synthetic_case())
        self.assertEqual(result["status"], "V")
        self.assertFalse(result["authorization"])

    def test_inapplicable(self):
        self.assertEqual(evaluate_sc04(synthetic_case("INAPPLICABLE"))["status"], "F")

    def test_wrong_revision_is_unknown_without_explicit_contradiction(self):
        case = synthetic_case()
        case["applicabilityAssertions"][0]["revision"] = "SYNTHETIC-R0"
        self.assertEqual(evaluate_sc04(case)["status"], "U")

    def test_untrusted_claim_unknown(self):
        case = synthetic_case()
        case["applicabilityAssertions"][0]["authority"] = "UNVERIFIED"
        self.assertEqual(evaluate_sc04(case)["status"], "U")

    def test_conflicting_applicability_fails(self):
        case = synthetic_case()
        conflict = dict(case["applicabilityAssertions"][0])
        conflict["verdict"] = "INAPPLICABLE"
        case["applicabilityAssertions"].append(conflict)
        self.assertEqual(evaluate_sc04(case)["status"], "F")

    def test_graphdb_unspecified_revision(self):
        report = {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                  "truncated": False, "facts": [{
                      "s": "urn:ebom", "p": "https://example.org/engineeringbom/hasRevision",
                      "o": "UNSPECIFIED", "g": "urn:engineering-bom"}]}
        result = assess_graphdb_sc04(report)
        self.assertEqual(result["status"], "U")
        self.assertEqual(result["evidence"][0]["classification"], "UNSPECIFIED_REVISION")


if __name__ == "__main__":
    unittest.main()
