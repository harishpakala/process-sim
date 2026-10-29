"""Conservative evidence-qualified resolution of operational references.

The caller supplies reviewed validation declarations. This module checks their
structure and association but does NOT independently authenticate evidence URIs.
Unreviewed mappings and unknown applicability remain non-authoritative.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from .contracts import Candidate, ResolutionResult

_SIGNAL = re.compile(r"(?<![A-Za-z])X(MEAS|MV)[-_]?(\d+)(?!\d)", re.I)
_STATES = {"validated", "unverified", "rejected"}
_APPLICABILITY = {"applicable", "inapplicable", "unknown"}


def extract_signal(reference: str) -> str | None:
    """Recognize legacy TEP operational references; recognition is not validation."""
    if not isinstance(reference, str):
        raise ValueError("Operational reference must be a string")
    match = _SIGNAL.search(reference)
    if not match:
        return None
    kind, index = match.group(1).upper(), int(match.group(2))
    if not 1 <= index <= (41 if kind == "MEAS" else 12):
        return None
    return f"X{kind}{index}"


def _declaration(value):
    if not isinstance(value, Mapping):
        raise ValueError("Declaration must be a mapping")
    required = {"requestedProperty", "signal", "reference", "validationStatus",
                "applicabilityStatus", "evidenceReferences"}
    if set(value) != required:
        raise ValueError("Declaration fields do not match the contract")
    if any(not isinstance(value[key], str) or not value[key].strip()
           for key in ("requestedProperty", "signal", "reference")):
        raise ValueError("Invalid declaration identifiers")
    if value["validationStatus"] not in _STATES:
        raise ValueError("Unknown validation status")
    if value["applicabilityStatus"] not in _APPLICABILITY:
        raise ValueError("Unknown applicability status")
    evidence = value["evidenceReferences"]
    if not isinstance(evidence, (list, tuple)) or any(
            not isinstance(e, str) or not e.strip() for e in evidence):
        raise ValueError("Invalid evidence references")
    if value["validationStatus"] == "validated" and not evidence:
        raise ValueError("Validated declarations require evidence references")
    if extract_signal(value["reference"]) != value["signal"]:
        raise ValueError("Declaration signal does not match its operational reference")
    return value


def resolve_correspondence(requested_property: str, references, declarations=()):
    """Resolve candidate signals without treating uniqueness as validation.

    A validated result requires exactly one eligible signal and no conflicting
    declarations for that signal. Multiple eligible signals remain ambiguous.
    Rejected, unverified, or inapplicable candidates are never selected.
    """
    if not isinstance(requested_property, str) or not requested_property.strip():
        raise ValueError("Requested property is required")
    if not isinstance(references, (list, tuple)) or any(
            not isinstance(r, str) for r in references):
        raise ValueError("References must be a sequence of strings")
    validated_declarations = [_declaration(d) for d in declarations]
    candidates = []
    for reference in sorted(set(references)):
        signal = extract_signal(reference)
        if signal is None:
            continue
        matching = [d for d in validated_declarations
                    if d["requestedProperty"] == requested_property
                    and d["signal"] == signal and d["reference"] == reference]
        states = {(d["validationStatus"], d["applicabilityStatus"]) for d in matching}
        # Disagreement is not resolved by choosing the most permissive claim.
        conflict = len(states) > 1
        if len(matching) == 1:
            state, applicability = next(iter(states))
        else:
            state, applicability = "unverified", "unknown"
        if conflict:
            state, applicability = "unverified", "unknown"
        evidence = tuple(sorted({e for d in matching for e in d["evidenceReferences"]}))
        candidates.append(Candidate(
            signal=signal, reference=reference,
            validation_status=state, applicability_status=applicability,
            evidence_references=evidence,
            reason=("conflicting declarations" if conflict else
                    "no unique reviewed declaration" if len(matching) != 1 else
                    "reviewed declaration; evidence authenticity not checked here"),
        ))
    eligible = {c.signal for c in candidates if c.validation_status == "validated"
                and c.applicability_status == "applicable"}
    # A competing unqualified candidate prevents an authoritative choice:
    # the system cannot assume it is irrelevant without additional evidence.
    all_signals = {c.signal for c in candidates if c.validation_status != "rejected"}
    if len(eligible) == 1 and all_signals == eligible and all(
            c.validation_status == "validated" and
            c.applicability_status == "applicable"
            for c in candidates if c.validation_status != "rejected"):
        return ResolutionResult(requested_property, "validated",
                                tuple(candidates), next(iter(eligible)))
    status = "ambiguous" if len(all_signals) > 1 else "unresolved"
    return ResolutionResult(requested_property, status, tuple(candidates))
