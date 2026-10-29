"""Dependency-aware recomposition planning for SELiRA contract instances.

This is a pure impact planner, not a GraphDB change listener. Dependency tokens
must be provided by validated source/contract query tracking; incomplete token
coverage cannot justify selective revalidation correctness.
"""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, order=True)
class ContractKey:
    correspondence_id: str
    contract_id: str


@dataclass(frozen=True)
class ImpactPlan:
    affected_evaluations: frozenset[ContractKey]
    affected_correspondences: frozenset[str]
    full_revalidation_required: bool
    reason: str


def plan_impact(
    changed_tokens: frozenset[str],
    dependencies: Mapping[ContractKey, frozenset[str]],
    *,
    dependencies_complete: bool,
    known_evaluations: frozenset[ContractKey],
) -> ImpactPlan:
    """Compute sound candidate set given an *externally attested* dependency map.

    If dependency coverage is not attested, conservatively schedule every
    known evaluation. Tokens can represent queries, absent-match scopes,
    contract/authority revisions, and RDF predicates as well as concrete triples.
    """
    if not dependencies_complete or not known_evaluations.issubset(dependencies):
        affected = known_evaluations
        full = True
        reason = "DEPENDENCIES_INCOMPLETE"
    else:
        affected = frozenset(
            key for key in known_evaluations
            if changed_tokens.intersection(dependencies[key])
        )
        full = False
        reason = "DEPENDENCY_INTERSECTION"
    return ImpactPlan(
        frozenset(affected),
        frozenset(key.correspondence_id for key in affected),
        full, reason
    )
