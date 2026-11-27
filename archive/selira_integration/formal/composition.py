"""SELiRA conditional applicability and conjunctive contract composition.

Pure reference semantics for the proposed formal specification. This module
does not establish engineering authority or execute SHACL.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Mapping


class Outcome(str, Enum):
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Applicability(str, Enum):
    APPLIES = "APPLIES"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"
    UNKNOWN = "UNKNOWN"


class Role(str, Enum):
    MANDATORY = "MANDATORY"
    ADVISORY = "ADVISORY"


class LifecycleState(str, Enum):
    CURRENT = "CURRENT"
    PENDING_REVALIDATION = "PENDING_REVALIDATION"


@dataclass(frozen=True)
class RevisionContext:
    graph_revisions: tuple[tuple[str, str], ...]
    contract_revision: str
    authority_revision: str

    def __post_init__(self):
        if not self.graph_revisions or not self.contract_revision or not self.authority_revision:
            raise ValueError("Explicit graph, contract, and authority revisions required")
        if len({g for g, _ in self.graph_revisions}) != len(self.graph_revisions):
            raise ValueError("Duplicate graph revision keys")
        if any(not graph or not revision for graph, revision in self.graph_revisions):
            raise ValueError("Graph names and revision identifiers required")


@dataclass(frozen=True)
class ContractRule:
    contract_id: str
    version: str
    role: Role
    applicability: Applicability

    def __post_init__(self):
        if not self.contract_id or not self.version:
            raise ValueError("Contract identifier and version required")


@dataclass(frozen=True)
class ContractEvaluation:
    contract_id: str
    version: str
    correspondence_id: str
    revision: RevisionContext
    outcome: Outcome
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositionResult:
    correspondence_id: str
    revision: RevisionContext
    outcome: Outcome
    lifecycle_state: LifecycleState
    publishable_as_validated: bool
    reasons: tuple[str, ...]
    mandatory_results: tuple[tuple[str, Outcome], ...]
    advisory_results: tuple[tuple[str, Outcome], ...]
    missing_contracts: tuple[str, ...]


def conjunction(a: Outcome, b: Outcome) -> Outcome:
    """Associative, commutative four-outcome mandatory conjunction."""
    for outcome in (Outcome.INVALID, Outcome.INDETERMINATE,
                    Outcome.VALIDATED):
        if a == outcome or b == outcome:
            return outcome
    return Outcome.NOT_APPLICABLE


def _normalized(rule: ContractRule, evaluation: ContractEvaluation | None,
                correspondence_id: str, revision: RevisionContext) -> tuple[Outcome, str | None]:
    if rule.applicability == Applicability.DOES_NOT_APPLY:
        if evaluation is not None and evaluation.outcome != Outcome.NOT_APPLICABLE:
            raise ValueError(f"Conflicting applicability and evaluation: {rule.contract_id}")
        return Outcome.NOT_APPLICABLE, None
    if rule.applicability == Applicability.UNKNOWN:
        if evaluation is not None and evaluation.outcome != Outcome.INDETERMINATE:
            raise ValueError(f"Unknown applicability cannot establish result: {rule.contract_id}")
        return Outcome.INDETERMINATE, "UNKNOWN_APPLICABILITY"
    if evaluation is None:
        return Outcome.INDETERMINATE, "MISSING_EVALUATION"
    if evaluation.correspondence_id != correspondence_id or evaluation.revision != revision:
        raise ValueError(f"Correspondence/revision mismatch: {rule.contract_id}")
    if evaluation.contract_id != rule.contract_id or evaluation.version != rule.version:
        raise ValueError(f"Contract identifier/version mismatch: {rule.contract_id}")
    if evaluation.outcome == Outcome.NOT_APPLICABLE:
        raise ValueError(f"Applicable contract cannot report NOT_APPLICABLE: {rule.contract_id}")
    return evaluation.outcome, None


def compose(
    correspondence_id: str,
    revision: RevisionContext,
    rules: tuple[ContractRule, ...],
    evaluations: Mapping[str, ContractEvaluation],
    *,
    registry_approved: bool,
    registry_complete: bool,
    lifecycle_state: LifecycleState = LifecycleState.CURRENT,
    provenance_complete: bool = False,
) -> CompositionResult:
    """Compose approved policy-scoped outcomes, never infer policy from results.

    A missing/unapproved registry forces INDETERMINATE even if a known
    contract-level violation exists. Unknown applicability also yields U.
    """
    if not correspondence_id:
        raise ValueError("Correspondence ID required")
    ids = [rule.contract_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate contract rule")
    if set(evaluations) - set(ids):
        raise ValueError("Evaluations contain contracts outside declared registry")
    mandatory, advisory, missing, reasons = [], [], [], []
    for rule in sorted(rules, key=lambda item: item.contract_id):
        evaluation = evaluations.get(rule.contract_id)
        # Always check supplied evaluation identity/revision, including NA and UNKNOWN.
        if evaluation is not None and (
            evaluation.correspondence_id != correspondence_id
            or evaluation.revision != revision
            or evaluation.contract_id != rule.contract_id
            or evaluation.version != rule.version
        ):
            raise ValueError(f"Stale or mismatched evaluation: {rule.contract_id}")
        outcome, reason = _normalized(rule, evaluation, correspondence_id, revision)
        (mandatory if rule.role == Role.MANDATORY else advisory).append((rule.contract_id, outcome))
        if reason:
            reasons.append(f"{rule.contract_id}:{reason}")
            if reason == "MISSING_EVALUATION":
                missing.append(rule.contract_id)
    if not registry_approved or not registry_complete:
        aggregate = Outcome.INDETERMINATE
        reasons.append("REGISTRY_NOT_APPROVED_OR_INCOMPLETE")
    else:
        aggregate = Outcome.NOT_APPLICABLE
        for _, outcome in mandatory:
            aggregate = conjunction(aggregate, outcome)
    if lifecycle_state == LifecycleState.PENDING_REVALIDATION:
        reasons.append("PENDING_REVALIDATION")
    if not provenance_complete:
        reasons.append("PROVENANCE_NOT_ATTESTED")
    publishable = (
        aggregate == Outcome.VALIDATED
        and registry_approved and registry_complete
        and lifecycle_state == LifecycleState.CURRENT
        and provenance_complete
    )
    return CompositionResult(
        correspondence_id, revision, aggregate, lifecycle_state,
        publishable, tuple(reasons), tuple(mandatory),
        tuple(advisory), tuple(missing)
    )
