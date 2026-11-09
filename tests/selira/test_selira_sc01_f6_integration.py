"""F6 ↔ existing SC-01 snapshot integration tests."""

# Created: 2026-10-29
# Author: Harish
import unittest

from selira_integration.lifecycle import Snapshot
from selira_integration.formal.composition import Outcome
from selira_integration.formal.sc01_lifecycle_adapter import (
    advance, initialize,
)
from selira_integration.formal.state_machine import Phase


KW = dict(contract_revision="contracts-v1", authority_revision="authority-v1",
          policy_approved=True, provenance_attested=True)


class SC01F6IntegrationTests(unittest.TestCase):
    def test_reference_change_invalidates_then_revalidates(self):
        r1 = Snapshot("R1", {"asset:A": "product:x"},
                      {"catalog:X": "product:x"})
        r2 = Snapshot("R2", {"asset:A": "product:y"},
                      {"catalog:X": "product:x"})
        states = initialize(r1, **KW)
        self.assertTrue(states["asset:A"].current_certification)
        result = advance(r1, r2, states, **KW)
        self.assertTrue(result.matches_full_baseline)
        state = result.states["asset:A"]
        self.assertEqual(state.phase, Phase.CURRENT)
        self.assertEqual(state.current_record.outcome, Outcome.INVALID)
        self.assertFalse(state.current_certification)
        self.assertEqual(len(state.history), 2)

    def test_incomplete_catalog_is_indeterminate(self):
        r1 = Snapshot("R1", {"asset:A": "product:x"}, {}, complete=False)
        state = initialize(r1, **KW)["asset:A"]
        self.assertEqual(state.current_record.outcome, Outcome.INDETERMINATE)
        self.assertFalse(state.current_certification)

    def test_removed_assignment_is_not_applicable(self):
        r1 = Snapshot("R1", {"asset:A": "product:x"},
                      {"catalog:X": "product:x"})
        r2 = Snapshot("R2", {}, {"catalog:X": "product:x"})
        result = advance(r1, r2, initialize(r1, **KW), **KW)
        self.assertTrue(result.matches_full_baseline)
        self.assertEqual(result.states["asset:A"].current_record.outcome,
                         Outcome.NOT_APPLICABLE)

    def test_unattested_policy_cannot_certify(self):
        r1 = Snapshot("R1", {"asset:A": "product:x"},
                      {"catalog:X": "product:x"})
        state = initialize(r1, **{**KW, "policy_approved": False})["asset:A"]
        self.assertEqual(state.current_record.outcome, Outcome.INDETERMINATE)
        self.assertFalse(state.current_certification)

    def test_conservative_fallback_checks_all(self):
        r1 = Snapshot("R1", {"asset:A": "product:x", "asset:B": "product:y"},
                      {"catalog:X": "product:x", "catalog:Y": "product:y"})
        r2 = Snapshot("R2", dict(r1.assigned), dict(r1.catalog))
        result = advance(r1, r2, initialize(r1, **KW), **KW)
        self.assertEqual(result.selective_evaluations, 2)
        self.assertTrue(result.matches_full_baseline)


if __name__ == "__main__":
    unittest.main()
