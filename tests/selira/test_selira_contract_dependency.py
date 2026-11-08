"""Dependency impact tests; coverage must be externally attested."""

# Created: 2026-10-29
# Author: Harish
import unittest
from selira_integration.formal.dependency import ContractKey, plan_impact


class DependencyTests(unittest.TestCase):
    def test_selects_affected_contract_only(self):
        a = ContractKey("C-101", "SC-01")
        b = ContractKey("C-101", "SC-04")
        c = ContractKey("C-102", "SC-01")
        result = plan_impact(
            frozenset({"catalog:identifier:x"}),
            {a: frozenset({"catalog:identifier:x"}),
             b: frozenset({"configured:range"}),
             c: frozenset({"catalog:identifier:y"})},
            dependencies_complete=True, known_evaluations=frozenset({a,b,c}))
        self.assertEqual(result.affected_evaluations, frozenset({a}))
        self.assertEqual(result.affected_correspondences, frozenset({"C-101"}))
        self.assertFalse(result.full_revalidation_required)

    def test_incomplete_dependencies_force_full(self):
        a = ContractKey("C-101", "SC-01")
        b = ContractKey("C-102", "SC-01")
        result = plan_impact(frozenset({"catalog:new-duplicate"}),
            {a: frozenset({"catalog:identifier:x"})},
            dependencies_complete=True, known_evaluations=frozenset({a,b}))
        self.assertTrue(result.full_revalidation_required)
        self.assertEqual(result.affected_evaluations, frozenset({a,b}))

    def test_new_match_query_scope(self):
        a = ContractKey("C-101", "SC-01")
        result = plan_impact(frozenset({"query:catalog:identifier:x"}),
            {a: frozenset({"query:catalog:identifier:x"})},
            dependencies_complete=True, known_evaluations=frozenset({a}))
        self.assertEqual(result.affected_evaluations, frozenset({a}))


if __name__ == "__main__":
    unittest.main()
