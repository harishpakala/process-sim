"""F7 controlled SC-01 equivalence checks against full revalidation."""

# Created: 2026-10-29
# Author: Harish
import itertools
import unittest

from selira_integration.lifecycle import Snapshot
from selira_integration.formal.selective_sc01 import compare


class SelectiveEquivalenceTests(unittest.TestCase):
    def test_exhaustive_small_snapshot_pairs(self):
        # 4 assignment choices x 9 catalog choices = 36 states, 1296 pairs.
        assignments = (None, "id:x", "id:y", "id:z")
        catalog_options = (None, "id:x", "id:y")
        snapshots = []
        for assigned, c1, c2 in itertools.product(
            assignments, catalog_options, catalog_options
        ):
            catalog = {}
            if c1 is not None:
                catalog["catalog:1"] = c1
            if c2 is not None:
                catalog["catalog:2"] = c2
            snapshots.append(Snapshot(
                "R1", {"asset:A": assigned} if assigned is not None else {},
                catalog, complete=True
            ))
        for old, new in itertools.product(snapshots, repeat=2):
            after = Snapshot("R2", new.assigned, new.catalog, new.complete)
            report = compare(old, after, coverage_attested=True,
                             policy_unchanged=True, authority_unchanged=True)
            self.assertTrue(report.equivalent,
                            msg=f"counterexample: {old} -> {after}")

    def test_selective_reduces_evaluations_on_unrelated_change(self):
        old = Snapshot("R1", {"A": "id:x", "B": "id:y"},
                       {"X": "id:x", "Y": "id:y"})
        new = Snapshot("R2", dict(old.assigned),
                       {"X": "id:x", "Y": "id:y", "Z": "id:z"})
        report = compare(old, new, coverage_attested=True,
                         policy_unchanged=True, authority_unchanged=True)
        self.assertTrue(report.equivalent)
        self.assertEqual(report.selective_evaluations, 0)
        self.assertEqual(report.full_evaluations, 2)

    def test_unattested_coverage_forces_full(self):
        old = Snapshot("R1", {"A": "id:x"}, {})
        new = Snapshot("R2", {"A": "id:x"}, {"X": "id:x"})
        report = compare(old, new, coverage_attested=False,
                         policy_unchanged=True, authority_unchanged=True)
        self.assertTrue(report.full_fallback)
        self.assertEqual(report.selective_evaluations, 1)
        self.assertTrue(report.equivalent)

    def test_authority_change_forces_full(self):
        old = Snapshot("R1", {"A": "id:x"}, {"X": "id:x"})
        new = Snapshot("R2", {"A": "id:x"}, {"X": "id:x"})
        report = compare(old, new, coverage_attested=True,
                         policy_unchanged=True, authority_unchanged=False)
        self.assertTrue(report.full_fallback)
        self.assertTrue(report.equivalent)

    def test_catalog_completeness_change(self):
        old = Snapshot("R1", {"A": "id:x"}, {}, complete=False)
        new = Snapshot("R2", {"A": "id:x"}, {}, complete=True)
        report = compare(old, new, coverage_attested=True,
                         policy_unchanged=True, authority_unchanged=True)
        self.assertTrue(report.equivalent)
        self.assertEqual(report.selective_evaluations, 1)


if __name__ == "__main__":
    unittest.main()
