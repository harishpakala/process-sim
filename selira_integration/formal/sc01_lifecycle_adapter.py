"""F6 integration adapter for the existing SC-01 snapshot evaluator.

This is a local, read-only reference integration. Revision authority and
catalog completeness must be independently attested by the caller.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

from dataclasses import dataclass

from selira_integration.lifecycle import Snapshot, check, detect, impacted
from .composition import (
    Applicability, ContractEvaluation, ContractRule, Outcome, RevisionContext,
    Role, compose,
)
from .state_machine import (
    CorrespondenceState, change, create, validation_complete,
)


@dataclass(frozen=True)
class SC01Transition:
    states: dict[str, CorrespondenceState]
    changed_assets: frozenset[str]
    selective_evaluations: int
    full_evaluations: int
    matches_full_baseline: bool


def revision_context(snapshot: Snapshot, *, contract_revision: str,
                     authority_revision: str) -> RevisionContext:
    return RevisionContext(
        (("asset-inventory-and-product-catalog-snapshot", snapshot.revision),),
        contract_revision, authority_revision,
    )


def _evaluate(snapshot: Snapshot, asset: str, revision: RevisionContext,
              *, policy_approved: bool, provenance_attested: bool):
    assigned = asset in snapshot.assigned
    # SC-01's rule concerns an assigned reference. Non-assigned assets are NA
    # even when catalog completeness is unknown.
    applicability = (Applicability.APPLIES if assigned
                     else Applicability.DOES_NOT_APPLY)
    rules = (ContractRule("SC-01", "1", Role.MANDATORY, applicability),)
    evaluations = {}
    if assigned:
        # An incomplete catalog cannot establish a unique-match violation.
        outcome = Outcome(check(snapshot, asset))
        evaluations["SC-01"] = ContractEvaluation(
            "SC-01", "1", asset, revision, outcome
        )
    return compose(
        asset, revision, rules, evaluations,
        registry_approved=policy_approved,
        registry_complete=policy_approved,
        provenance_complete=provenance_attested,
    )


def initialize(snapshot: Snapshot, *, contract_revision: str,
               authority_revision: str, policy_approved: bool,
               provenance_attested: bool) -> dict[str, CorrespondenceState]:
    rev = revision_context(snapshot, contract_revision=contract_revision,
                           authority_revision=authority_revision)
    return {
        asset: validation_complete(
            create(asset, rev),
            _evaluate(snapshot, asset, rev, policy_approved=policy_approved,
                      provenance_attested=provenance_attested),
        )
        for asset in sorted(snapshot.assigned)
    }


def advance(
    before: Snapshot,
    after: Snapshot,
    states: dict[str, CorrespondenceState],
    *,
    contract_revision: str,
    authority_revision: str,
    policy_approved: bool,
    provenance_attested: bool,
    dependency_coverage_attested: bool = False,
) -> SC01Transition:
    """Advance SC-01 evaluations, conservatively handling unknown dependencies.

    When dependency coverage is not attested, revalidate *all* assigned assets.
    A removed assignment is re-evaluated as NA and retained as a historical
    correspondence record. Unaffected evaluations are NOT re-certified at the
    new revision: they retain historical records until an F7-safe carry-forward
    operation is defined. This prevents publishing stale R1 results as R2.
    """
    events = detect(before, after)
    before_assets = set(before.assigned)
    after_assets = set(after.assigned)
    universe = before_assets | after_assets | set(states)
    affected = (impacted(before, after, events) if dependency_coverage_attested
                else set(universe))
    # Changed revisions require new current records; revalidate all until
    # the F7 carry-forward semantics are implemented.
    if before.revision != after.revision:
        affected = set(universe)
    rev = revision_context(after, contract_revision=contract_revision,
                           authority_revision=authority_revision)
    updated = dict(states)
    for asset in sorted(affected):
        previous = updated.get(asset, create(asset, revision_context(
            before, contract_revision=contract_revision,
            authority_revision=authority_revision)))
        pending = change(previous, rev)
        updated[asset] = validation_complete(
            pending,
            _evaluate(after, asset, rev, policy_approved=policy_approved,
                      provenance_attested=provenance_attested),
        )
    baseline = {
        asset: _evaluate(after, asset, rev,
                         policy_approved=policy_approved,
                         provenance_attested=provenance_attested).outcome
        for asset in universe
    }
    agreement = all(
        asset in updated
        and updated[asset].current_record is not None
        and updated[asset].current_record.revision == rev
        and updated[asset].current_record.outcome == outcome
        for asset, outcome in baseline.items()
    )
    return SC01Transition(updated, frozenset(affected), len(affected),
                          len(universe), agreement)
