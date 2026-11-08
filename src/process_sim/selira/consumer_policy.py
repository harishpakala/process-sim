"""Fail-closed consumer policy for authoritative semantic use."""

# Created: 2026-10-28
# Author: Harish
from .contracts import ResolutionResult


def authorize_use(result: ResolutionResult) -> bool:
    """Allow authoritative use only for one validated, applicable signal."""
    if not isinstance(result, ResolutionResult):
        raise TypeError("Expected a SELiRA ResolutionResult")
    if result.resolution_status != "validated" or not result.selected_signal:
        return False
    if not result.candidates:
        return False
    active = [candidate for candidate in result.candidates
              if candidate.validation_status != "rejected"]
    return bool(active) and all(
        candidate.signal == result.selected_signal
        and candidate.validation_status == "validated"
        and candidate.applicability_status == "applicable"
        and bool(candidate.evidence_references)
        for candidate in active
    )
