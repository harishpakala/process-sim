"""F6 lifecycle transition safety regression tests."""

# Created: 2026-10-29
# Author: Harish
import unittest

from selira_integration.formal.composition import (
    Applicability, ContractEvaluation, ContractRule, Outcome, Role,
    RevisionContext, compose,
)
from selira_integration.formal.state_machine import (
    Phase, change, create, invalidate_current, validation_complete,
)


def revision(version):
    return RevisionContext((("inventory", version),), "contracts-v1", "authority-v1")


def result(rev, outcome=Outcome.VALIDATED):
    return compose(
        "C-101", rev,
        (ContractRule("SC-01", "1", Role.MANDATORY, Applicability.APPLIES),),
        {"SC-01": ContractEvaluation("SC-01", "1", "C-101", rev, outcome)},
        registry_approved=True, registry_complete=True, provenance_complete=True,
    )


class LifecycleTests(unittest.TestCase):
    def test_create_and_certify(self):
        r1 = revision("R1")
        state = create("C-101", r1)
        self.assertEqual(state.phase, Phase.UNVALIDATED)
        self.assertFalse(state.current_certification)
        state = validation_complete(state, result(r1))
        self.assertEqual(state.phase, Phase.CURRENT)
        self.assertTrue(state.current_certification)
        self.assertEqual(len(state.history), 1)

    def test_change_removes_current_certification_preserves_history(self):
        r1, r2 = revision("R1"), revision("R2")
        state = validation_complete(create("C-101", r1), result(r1))
        pending = change(state, r2)
        self.assertEqual(pending.phase, Phase.PENDING_REVALIDATION)
        self.assertFalse(pending.current_certification)
        self.assertIsNone(pending.current_record)
        self.assertEqual(len(pending.history), 1)
        with self.assertRaises(ValueError):
            validation_complete(pending, result(r1))
        current = validation_complete(pending, result(r2, Outcome.INVALID))
        self.assertEqual(current.current_record.outcome, Outcome.INVALID)
        self.assertEqual(len(current.history), 2)
        self.assertFalse(current.current_certification)

    def test_unknown_impact_conservatively_marks_pending(self):
        r1 = revision("R1")
        state = validation_complete(create("C-101", r1), result(r1))
        pending = invalidate_current(state)
        self.assertEqual(pending.phase, Phase.PENDING_REVALIDATION)
        self.assertFalse(pending.current_certification)

    def test_repeated_change_updates_target(self):
        r1, r2, r3 = revision("R1"), revision("R2"), revision("R3")
        state = change(change(create("C-101", r1), r2), r3)
        self.assertEqual(state.target_revision, r3)
        with self.assertRaises(ValueError):
            validation_complete(state, result(r2))

    def test_mismatched_correspondence_rejected(self):
        r1 = revision("R1")
        state = create("C-102", r1)
        with self.assertRaises(ValueError):
            validation_complete(state, result(r1))

    def test_indeterminate_is_reportable_but_not_certified(self):
        r1 = revision("R1")
        state = validation_complete(create("C-101", r1),
                                    result(r1, Outcome.INDETERMINATE))
        self.assertEqual(state.phase, Phase.CURRENT)
        self.assertFalse(state.current_certification)


if __name__ == "__main__":
    unittest.main()
