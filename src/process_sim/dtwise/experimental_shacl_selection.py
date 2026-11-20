"""Strict, provider-independent contract for single-domain LLM path selection.

This validates response shape and candidate membership, not whether the LLM's
semantic interpretation is correct. No network calls or SPARQL generation.
"""
from __future__ import annotations

import json
from typing import Any

STATUSES = frozenset({"selected", "ambiguous", "unresolved"})
FIELDS = frozenset({"status", "selected_candidate_ids", "reason"})


class SelectionContractError(ValueError):
    """LLM response violates the single-domain selection contract."""


def validate_selection(response: str | dict[str, Any], prepared: dict) -> dict:
    """Parse and validate a proposed selection against prepared SHACL IDs.

    selected: one or more unique, known candidate IDs.
    ambiguous/unresolved: no selected IDs; uncertainty is not a selection.
    """
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid JSON response") from exc
    if not isinstance(response, dict) or set(response) != FIELDS:
        raise SelectionContractError("Response must contain exactly status, selected_candidate_ids, reason")
    status = response["status"]
    ids = response["selected_candidate_ids"]
    reason = response["reason"]
    if not isinstance(status, str) or status not in STATUSES:
        raise SelectionContractError("Invalid status")
    if not isinstance(reason, str) or not reason.strip():
        raise SelectionContractError("Reason must be a nonempty string")
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise SelectionContractError("selected_candidate_ids must be a list of strings")
    if len(ids) != len(set(ids)):
        raise SelectionContractError("Duplicate candidate IDs")
    try:
        offered = [candidate["id"] for candidate in prepared["prompt"]["candidates"]]
        registry = prepared["registry"]
    except (KeyError, TypeError) as exc:
        raise SelectionContractError("Invalid prepared candidate payload") from exc
    if len(offered) != len(set(offered)) or set(offered) != set(registry):
        raise SelectionContractError("Candidate IDs and registry disagree")
    if any(item not in registry for item in ids):
        raise SelectionContractError("Unknown candidate ID")
    if status == "selected" and not ids:
        raise SelectionContractError("Selected status requires candidate IDs")
    if status != "selected" and ids:
        raise SelectionContractError("Uncertain status must not select candidates")
    return {"status": status, "selected_candidate_ids": ids, "reason": reason.strip()}
