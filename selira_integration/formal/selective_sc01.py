"""F7 experimental SC-01 selective-vs-full equivalence checker.

Reference algorithm over complete immutable snapshots. Not a proof of
general SHACL/SPARQL selective revalidation correctness.
"""

# Created: 2026-10-29
# Author: Harish
from dataclasses import dataclass

from selira_integration.lifecycle import Snapshot, check
from .dependency import ContractKey
from .sc01_dependencies import impact


@dataclass(frozen=True)
class EquivalenceReport:
    selective: dict[str, str]
    full: dict[str, str]
    affected: frozenset[str]
    selective_evaluations: int
    full_evaluations: int
    equivalent: bool
    full_fallback: bool


def compare(
    before: Snapshot,
    after: Snapshot,
    *,
    coverage_attested: bool,
    policy_unchanged: bool,
    authority_unchanged: bool,
) -> EquivalenceReport:
    """Compare selective outcomes to a fresh full baseline at the target revision.

    Precondition: complete immutable snapshots; SC-01 deterministic; no
    out-of-band policy/authority changes when reusing evaluations. Otherwise
    force full revalidation. Unassigned correspondences are retained as NA.
    """
    universe = set(before.assigned) | set(after.assigned)
    prior = {asset: check(before, asset) for asset in universe}
    plan = impact(before, after, coverage_attested=coverage_attested)
    fallback = (plan.full_revalidation_required or not policy_unchanged
                or not authority_unchanged)
    affected = (set(universe) if fallback else {
        key.correspondence_id for key in plan.affected_evaluations
        if key.contract_id == "SC-01"
    })
    selective = {
        asset: check(after, asset) if asset in affected else prior[asset]
        for asset in sorted(universe)
    }
    full = {asset: check(after, asset) for asset in sorted(universe)}
    return EquivalenceReport(
        selective, full, frozenset(affected), len(affected), len(universe),
        selective == full, fallback,
    )
