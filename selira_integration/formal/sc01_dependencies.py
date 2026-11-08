"""F5 SC-01 dependency capture including negative lookup scope.

Snapshot-specific reference implementation. The complete catalog must be
available to detect additions, removals and duplicate identifiers. This is
not yet a general SPARQL dependency extractor.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

from dataclasses import dataclass

from selira_integration.lifecycle import Snapshot
from .dependency import ContractKey, ImpactPlan, plan_impact


def assignment_token(asset: str) -> str:
    return "assigned:" + asset


def lookup_token(reference: str) -> str:
    """Query-scope token: covers *all* catalog matches, including zero matches."""
    return "catalog-lookup:" + reference


@dataclass(frozen=True)
class SC01DependencyCapture:
    dependencies: dict[ContractKey, frozenset[str]]
    known_evaluations: frozenset[ContractKey]


def capture(snapshot: Snapshot) -> SC01DependencyCapture:
    dependencies = {}
    for asset, reference in snapshot.assigned.items():
        dependencies[ContractKey(asset, "SC-01")] = frozenset({
            assignment_token(asset), lookup_token(reference)
        })
    return SC01DependencyCapture(dependencies, frozenset(dependencies))


def changed_tokens(before: Snapshot, after: Snapshot) -> frozenset[str]:
    tokens = set()
    for asset in before.assigned.keys() | after.assigned.keys():
        old, new = before.assigned.get(asset), after.assigned.get(asset)
        if old != new:
            tokens.add(assignment_token(asset))
            if old is not None:
                tokens.add(lookup_token(old))
            if new is not None:
                tokens.add(lookup_token(new))
    for product in before.catalog.keys() | after.catalog.keys():
        old, new = before.catalog.get(product), after.catalog.get(product)
        if old != new:
            if old is not None:
                tokens.add(lookup_token(old))
            if new is not None:
                tokens.add(lookup_token(new))
    if before.complete != after.complete:
        tokens.add("catalog-completeness")
    return frozenset(tokens)


def impact(before: Snapshot, after: Snapshot, *,
           coverage_attested: bool) -> ImpactPlan:
    old = capture(before)
    new = capture(after)
    known = old.known_evaluations | new.known_evaluations
    # Use both revision dependency sets so changes to assigned refs do not
    # escape the prior lookup scope.
    deps = {
        key: old.dependencies.get(key, frozenset())
             | new.dependencies.get(key, frozenset())
             | frozenset({"catalog-completeness"})
        for key in known
    }
    # A completeness flag is not itself proof of an exhaustive change feed.
    # Coverage must be attested by the snapshot/change-source integration.
    return plan_impact(changed_tokens(before, after), deps,
                       dependencies_complete=coverage_attested,
                       known_evaluations=known)
