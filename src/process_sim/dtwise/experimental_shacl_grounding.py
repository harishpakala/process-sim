"""Conservative deterministic checks for explicitly named SHACL properties.

This is not a general synonym detector. Only explicit schema-style property
references are treated as authoritative; free-language requests remain subject
to semantic retrieval and LLM selection.
"""
from __future__ import annotations

import re

# Restrict detection to CamelCase/PascalCase schema identifiers or quoted names.
_IDENTIFIER = r"[A-Z][A-Za-z0-9_]*"
_QUOTED = r"[\"']([^\"']+)[\"']"
_BEFORE = re.compile(r"\b(" + _IDENTIFIER + r")\s+propert(?:y|ies)\b")
_AFTER = re.compile(r"(?i:\bpropert(?:y|ies)\s+(?:named\s+|called\s+)?)(" + _IDENTIFIER + r")\b")
_QUOTED_AFTER = re.compile(r"\bpropert(?:y|ies)\s+(?:named\s+|called\s+)?" + _QUOTED, re.I)


def explicit_property_names(question: str) -> list[str]:
    """Extract only unambiguous schema-style property identifiers."""
    matches = []
    for pattern in (_BEFORE, _AFTER, _QUOTED_AFTER):
        matches.extend((match.start(1), match.group(1)) for match in pattern.finditer(question))
    return list(dict.fromkeys(name for _, name in sorted(matches)))


def property_grounding(index, question: str) -> dict:
    """Resolve explicit property names against the selected domain's index."""
    names = explicit_property_names(question)
    available = {prop["name"].casefold(): prop["name"]
                 for properties in index.properties.values() for prop in properties}
    missing = [name for name in names if name.casefold() not in available]
    return {"explicit_properties": names, "missing_properties": missing,
            "resolved_properties": [available[name.casefold()] for name in names
                                    if name.casefold() in available]}


def enforce_property_grounding(index, question: str, prepared: dict,
                               selection: dict) -> dict:
    """Fail closed on missing explicit properties or selected property mismatches."""
    grounding = property_grounding(index, question)
    if grounding["missing_properties"]:
        return {"status": "unresolved", "selected_candidate_ids": [],
                "reason": "Explicit SHACL property not found in domain: "
                          + ", ".join(grounding["missing_properties"])}
    if selection["status"] == "selected" and grounding["resolved_properties"]:
        expected = {name.casefold() for name in grounding["resolved_properties"]}
        actual = {prepared["registry"][candidate_id]["property"]["name"].casefold()
                  for candidate_id in selection["selected_candidate_ids"]}
        if not actual.issubset(expected):
            return {"status": "unresolved", "selected_candidate_ids": [],
                    "reason": "Selected candidate property contradicts explicit SHACL property"}
    return selection
