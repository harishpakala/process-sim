"""Explicit, evidence-bearing alignment declarations.

ECLASS IRDIs identify terms only. No mappings are populated automatically from
names, catalog strings, ECLASS classes, or coincident signal identifiers.
"""
from __future__ import annotations

from collections.abc import Mapping

REQUIRED = frozenset({
    "catalogPropertyIri", "catalogPropertyTermIrdi", "signal",
    "measuredQuantityTermIrdi", "unit", "evidenceReference",
    "verificationStatus", "applicability",
})
STATUSES = frozenset({"proposed", "verified", "rejected"})

def validate_alignment(entry):
    if not isinstance(entry, Mapping) or set(entry) != REQUIRED:
        raise ValueError("Alignment must contain exactly the required evidence fields")
    for key in REQUIRED:
        if not isinstance(entry[key], str) or not entry[key].strip() or len(entry[key]) > 2048:
            raise ValueError("Missing or invalid alignment field: " + key)
    if entry["verificationStatus"] not in STATUSES:
        raise ValueError("Invalid verification status")
    if not entry["catalogPropertyIri"].startswith(("http://", "https://")):
        raise ValueError("Catalog property must have an absolute HTTP IRI")
    if not entry["evidenceReference"].startswith(("http://", "https://")):
        raise ValueError("Evidence must have an absolute HTTP IRI")
    return dict(entry)

def assess_alignments(properties, signal, declarations=()):
    """Report evidence without inferring equivalence or numerical constraints.

    Verified declarations can authorize a *candidate* comparison, but a
    separate unit/applicability evaluator is still required.
    """
    validated = [validate_alignment(item) for item in declarations]
    output = []
    for prop in properties:
        matches = [entry for entry in validated
                   if entry["catalogPropertyIri"] == prop.get("iri")
                   and entry["signal"] == signal
                   and entry["catalogPropertyTermIrdi"] in (
                       prop.get("semanticIds", []) + prop.get("supplementalSemanticIds", []))]
        verified = [entry for entry in matches if entry["verificationStatus"] == "verified"]
        output.append({
            "catalogPropertyIri": prop.get("iri"),
            "signal": signal,
            "status": "verified_alignment" if len(verified) == 1 else
                      "conflicting_evidence" if len(verified) > 1 else
                      "unverified",
            "evidence": matches,
            "comparisonAuthorized": False,
            "reason": "Numeric comparisons require separate unit, value, and applicability validation",
        })
    return output
