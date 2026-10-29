"""Exhaustive algebra and policy tests for SELiRA contract composition."""
import itertools
import unittest
from selira_integration.formal.composition import (
    Outcome as O, Applicability as A, Role, LifecycleState as L,
    RevisionContext, ContractRule, ContractEvaluation, conjunction, compose,
)

R = RevisionContext((("inventory", "R1"), ("catalog", "R1")), "contracts-v1", "authority-v1")


def rule(name, applicability=A.APPLIES, role=Role.MANDATORY):
    return ContractRule(name, "1", role, applicability)


def evaluation(name, outcome, revision=R, correspondence="C-101"):
    return ContractEvaluation(name, "1", correspondence, revision, outcome, ("evidence:1",))


def run(rules, evaluations=None, **kwargs):
    return compose("C-101", R, tuple(rules), evaluations or {},
                   registry_approved=kwargs.pop("approved", True),
                   registry_complete=kwargs.pop("complete", True),
                   provenance_complete=kwargs.pop("provenance", True),
                   **kwargs)


class CompositionTests(unittest.TestCase):
    def test_all_sixteen_cells(self):
        values = list(O)
        expected = {
            (O.VALIDATED, O.VALIDATED): O.VALIDATED,
            (O.VALIDATED, O.INVALID): O.INVALID,
            (O.VALIDATED, O.INDETERMINATE): O.INDETERMINATE,
            (O.VALIDATED, O.NOT_APPLICABLE): O.VALIDATED,
            (O.INVALID, O.INVALID): O.INVALID,
            (O.INVALID, O.INDETERMINATE): O.INVALID,
            (O.INVALID, O.NOT_APPLICABLE): O.INVALID,
            (O.INDETERMINATE, O.INDETERMINATE): O.INDETERMINATE,
            (O.INDETERMINATE, O.NOT_APPLICABLE): O.INDETERMINATE,
            (O.NOT_APPLICABLE, O.NOT_APPLICABLE): O.NOT_APPLICABLE,
        }
        for a, b in itertools.product(values, repeat=2):
            self.assertEqual(conjunction(a, b), expected.get((a, b), expected.get((b, a))))

    def test_algebraic_properties(self):
        for a, b, c in itertools.product(O, repeat=3):
            self.assertEqual(conjunction(a, b), conjunction(b, a))
            self.assertEqual(conjunction(conjunction(a, b), c),
                             conjunction(a, conjunction(b, c)))
            self.assertEqual(conjunction(a, a), a)
            self.assertEqual(conjunction(a, O.NOT_APPLICABLE), a)

    def test_mandatory_violation_and_order_independence(self):
        rules = [rule("SC-01"), rule("SC-04"), rule("SC-06")]
        evaluations = {"SC-01": evaluation("SC-01", O.VALIDATED),
                       "SC-04": evaluation("SC-04", O.INVALID),
                       "SC-06": evaluation("SC-06", O.INDETERMINATE)}
        for permutation in itertools.permutations(rules):
            result = run(permutation, evaluations)
            self.assertEqual(result.outcome, O.INVALID)
            self.assertFalse(result.publishable_as_validated)

    def test_missing_required_and_unknown_applicability(self):
        result = run([rule("SC-01"), rule("SC-03")],
                     {"SC-01": evaluation("SC-01", O.VALIDATED)})
        self.assertEqual(result.outcome, O.INDETERMINATE)
        self.assertEqual(result.missing_contracts, ("SC-03",))
        result = run([rule("SC-01", A.UNKNOWN)])
        self.assertEqual(result.outcome, O.INDETERMINATE)

    def test_registry_incomplete_overrides_known_violation(self):
        result = run([rule("SC-04")],
                     {"SC-04": evaluation("SC-04", O.INVALID)}, complete=False)
        self.assertEqual(result.outcome, O.INDETERMINATE)
        self.assertEqual(result.mandatory_results, (("SC-04", O.INVALID),))

    def test_no_vacuous_validation(self):
        self.assertEqual(run([]).outcome, O.NOT_APPLICABLE)
        self.assertEqual(run([rule("SC-01", A.DOES_NOT_APPLY)]).outcome,
                         O.NOT_APPLICABLE)

    def test_advisory_does_not_override_mandatory(self):
        result = run([rule("SC-01"), rule("SC-04", role=Role.ADVISORY)],
                     {"SC-01": evaluation("SC-01", O.VALIDATED),
                      "SC-04": evaluation("SC-04", O.INVALID)})
        self.assertEqual(result.outcome, O.VALIDATED)
        self.assertEqual(result.advisory_results, (("SC-04", O.INVALID),))

    def test_pending_or_unattested_cannot_certify(self):
        args = ([rule("SC-01")], {"SC-01": evaluation("SC-01", O.VALIDATED)})
        self.assertTrue(run(*args).publishable_as_validated)
        self.assertFalse(run(*args, lifecycle_state=L.PENDING_REVALIDATION).publishable_as_validated)
        self.assertFalse(run(*args, provenance=False).publishable_as_validated)

    def test_stale_revision_rejected(self):
        stale = RevisionContext((("inventory", "R2"),), "contracts-v1", "authority-v1")
        with self.assertRaises(ValueError):
            run([rule("SC-01")], {"SC-01": evaluation("SC-01", O.VALIDATED, stale)})

    def test_conflicting_applicability_rejected(self):
        with self.assertRaises(ValueError):
            run([rule("SC-01", A.DOES_NOT_APPLY)],
                {"SC-01": evaluation("SC-01", O.VALIDATED)})

    def test_duplicate_and_undeclared_rejected(self):
        with self.assertRaises(ValueError):
            run([rule("SC-01"), rule("SC-01")])
        with self.assertRaises(ValueError):
            run([rule("SC-01")], {"SC-02": evaluation("SC-02", O.VALIDATED)})


if __name__ == "__main__":
    unittest.main()
