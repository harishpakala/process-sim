import unittest
from experiments.dtwise_phase6_path_assessment import assess, hypothesis_path


class Phase6PathAssessmentTests(unittest.TestCase):
    def test_hypothesis_path_is_not_evidence(self):
        audit = {
            "candidate_shapes": {
                "s0": {"properties": []},
                "s1": {"properties": [{"predicate": "urn:p"}]},
            },
            "plan": {"fields": [{"name": "v", "shape": "s0", "predicate": "urn:p"}]},
            "join_candidates": {"j0": {"left": "s0", "right": "s1",
                                      "evidence": "RDF-term equality is a hypothesis"}},
        }
        result = assess(audit)[0]
        self.assertEqual(result["repair_decision"], "ambiguous_unverified_alternatives")
        self.assertEqual(result["alternatives_assessed"][0]["hypothesis_path"], ["j0"])
        self.assertFalse(result["alternatives_assessed"][0]["verified_evidence"])
        self.assertFalse(result["auto_repaired"])
        self.assertEqual(audit["plan"]["fields"][0]["shape"], "s0")

    def test_no_candidate_path_still_not_repaired(self):
        audit = {"candidate_shapes": {
            "s0": {"properties": []},
            "s1": {"properties": [{"predicate": "urn:p"}]}},
            "plan": {"fields": [{"name": "v", "shape": "s0", "predicate": "urn:p"}]}}
        result = assess(audit)[0]
        self.assertEqual(result["alternatives_assessed"][0]["connectivity"], "no_candidate_path")
        self.assertFalse(result["join_verified"])

    def test_missing_predicate_fail_closed(self):
        audit = {"candidate_shapes": {"s0": {"properties": []}},
                 "plan": {"fields": [{"name": "v", "shape": "s0", "predicate": "urn:missing"}]}}
        self.assertEqual(assess(audit)[0]["repair_decision"], "unsupported_in_candidate_schema")

    def test_valid_field_needs_no_repair(self):
        audit = {"candidate_shapes": {"s0": {"properties": [{"predicate": "urn:p"}]}},
                 "plan": {"fields": [{"name": "v", "shape": "s0", "predicate": "urn:p"}]}}
        self.assertEqual(assess(audit)[0]["repair_decision"], "no_repair_needed")

    def test_multi_hop_hypothesis_path(self):
        edges = {"j0": {"left": "s0", "right": "s1"},
                 "j1": {"left": "s1", "right": "s2"}}
        self.assertEqual(hypothesis_path(edges, "s0", "s2"), ["j0", "j1"])
        self.assertIsNone(hypothesis_path(edges, "s0", "s3"))


if __name__ == "__main__":
    unittest.main()
