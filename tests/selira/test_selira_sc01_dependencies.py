"""F5 tests for negative lookup scopes and duplicate introduction."""
import unittest

from selira_integration.lifecycle import Snapshot, check
from selira_integration.formal.dependency import ContractKey
from selira_integration.formal.sc01_dependencies import impact


class SC01DependencyTests(unittest.TestCase):
    def test_new_duplicate_invalidates_previous_unique_match(self):
        before = Snapshot("R1", {"asset:A": "id:x"}, {"catalog:1": "id:x"})
        after = Snapshot("R2", {"asset:A": "id:x"},
                         {"catalog:1": "id:x", "catalog:2": "id:x"})
        self.assertEqual(check(before, "asset:A"), "VALIDATED")
        self.assertEqual(check(after, "asset:A"), "INVALID")
        plan = impact(before, after, coverage_attested=True)
        self.assertEqual(plan.affected_evaluations,
                         frozenset({ContractKey("asset:A", "SC-01")}))

    def test_zero_to_one_match_triggers_revalidation(self):
        before = Snapshot("R1", {"asset:A": "id:x"}, {})
        after = Snapshot("R2", {"asset:A": "id:x"}, {"catalog:1": "id:x"})
        self.assertEqual(check(before, "asset:A"), "INVALID")
        self.assertEqual(check(after, "asset:A"), "VALIDATED")
        plan = impact(before, after, coverage_attested=True)
        self.assertIn(ContractKey("asset:A", "SC-01"),
                      plan.affected_evaluations)

    def test_unrelated_catalog_change_does_not_trigger(self):
        before = Snapshot("R1", {"asset:A": "id:x"},
                          {"catalog:1": "id:x"})
        after = Snapshot("R2", {"asset:A": "id:x"},
                         {"catalog:1": "id:x", "catalog:2": "id:y"})
        plan = impact(before, after, coverage_attested=True)
        self.assertFalse(plan.affected_evaluations)

    def test_incomplete_coverage_forces_full(self):
        before = Snapshot("R1", {"asset:A": "id:x"}, {})
        after = Snapshot("R2", {"asset:A": "id:x"}, {})
        plan = impact(before, after, coverage_attested=False)
        self.assertTrue(plan.full_revalidation_required)
        self.assertEqual(len(plan.affected_evaluations), 1)

    def test_catalog_completeness_change_impacts_every_assignment(self):
        before = Snapshot("R1", {"asset:A": "id:x"}, {}, complete=False)
        after = Snapshot("R2", {"asset:A": "id:x"}, {}, complete=True)
        plan = impact(before, after, coverage_attested=True)
        self.assertEqual(len(plan.affected_evaluations), 1)


if __name__ == "__main__":
    unittest.main()
