"""F6: pure, immutable revision-aware correspondence lifecycle transitions."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .composition import CompositionResult, Outcome, RevisionContext


class Phase(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    CURRENT = "CURRENT"
    PENDING_REVALIDATION = "PENDING_REVALIDATION"


@dataclass(frozen=True)
class ValidationRecord:
    revision: RevisionContext
    outcome: Outcome
    publishable_as_validated: bool


@dataclass(frozen=True)
class CorrespondenceState:
    correspondence_id: str
    phase: Phase
    target_revision: RevisionContext
    current_record: ValidationRecord | None = None
    history: tuple[ValidationRecord, ...] = ()

    @property
    def current_certification(self) -> bool:
        return (self.phase == Phase.CURRENT
                and self.current_record is not None
                and self.current_record.revision == self.target_revision
                and self.current_record.outcome == Outcome.VALIDATED
                and self.current_record.publishable_as_validated)


def create(correspondence_id: str, revision: RevisionContext) -> CorrespondenceState:
    if not correspondence_id:
        raise ValueError("Correspondence identifier required")
    return CorrespondenceState(correspondence_id, Phase.UNVALIDATED, revision)


def change(state: CorrespondenceState, new_revision: RevisionContext) -> CorrespondenceState:
    """Relevant or conservatively presumed relevant change; historical record preserved."""
    if new_revision == state.target_revision:
        return state
    return replace(state, phase=Phase.PENDING_REVALIDATION,
                   target_revision=new_revision, current_record=None)


def invalidate_current(state: CorrespondenceState) -> CorrespondenceState:
    """Unknown impact: never expose a prior result as a current certification."""
    return replace(state, phase=Phase.PENDING_REVALIDATION, current_record=None)


def validation_complete(state: CorrespondenceState,
                        result: CompositionResult) -> CorrespondenceState:
    if result.correspondence_id != state.correspondence_id:
        raise ValueError("Correspondence mismatch")
    if result.revision != state.target_revision:
        raise ValueError("Stale or future revision result")
    if result.lifecycle_state.value == "PENDING_REVALIDATION":
        raise ValueError("Cannot complete lifecycle using a pending composition result")
    record = ValidationRecord(result.revision, result.outcome,
                              result.publishable_as_validated)
    return replace(state, phase=Phase.CURRENT, current_record=record,
                   history=state.history + (record,))
