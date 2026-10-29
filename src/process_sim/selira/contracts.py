"""Small, serializable SELiRA correspondence contract.

Resolution is response-level; validation and applicability are candidate-level.
No implicit promotion from a recognized operational reference to validation.
"""
from dataclasses import asdict, dataclass
from typing import Literal

Validation = Literal["validated", "unverified", "rejected"]
Applicability = Literal["applicable", "inapplicable", "unknown"]
Resolution = Literal["validated", "ambiguous", "unresolved"]


@dataclass(frozen=True)
class Candidate:
    signal: str
    reference: str
    validation_status: Validation
    applicability_status: Applicability
    evidence_references: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ResolutionResult:
    requested_property: str
    resolution_status: Resolution
    candidates: tuple[Candidate, ...]
    selected_signal: str | None = None

    def to_dict(self):
        return asdict(self)
