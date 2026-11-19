"""Strict Phase 1 query-plan contract; no LLM invocation or SPARQL generation.

Intentionally separate from the existing path-selection contract until the
new Qwen prompt and concept-ending candidates are implemented.
"""
from __future__ import annotations

import json
from typing import Any

from process_sim.dtwise.experimental_shacl_selection import (
    SelectionContractError, validate_selection,
)

PHASE1_OPERATIONS = frozenset({"RETRIEVE", "COUNT", "EXISTS"})
PLAN_FIELDS = frozenset({
    "status", "selected_candidate_ids", "operation", "target", "modifiers", "reason",
})
TARGET_FIELDS = frozenset({"candidate_id", "node_index", "kind"})


def validate_query_plan(response: str | dict[str, Any], prepared: dict) -> dict:
    """Validate a proposed intent and bound target against offered SHACL paths.

    Targets are explicit node positions or the verified terminal property.
    No predicate IRIs or arbitrary SPARQL text are accepted from Qwen.
    """
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid JSON query plan") from exc
    if not isinstance(response, dict) or set(response) != PLAN_FIELDS:
        raise SelectionContractError("Query plan has unexpected or missing fields")

    selection = validate_selection({
        "status": response["status"],
        "selected_candidate_ids": response["selected_candidate_ids"],
        "reason": response["reason"],
    }, prepared)
    operation = response["operation"]
    if operation is not None and (
        not isinstance(operation, str) or operation not in PHASE1_OPERATIONS
    ):
        raise SelectionContractError("Unsupported Phase 1 operation")
    if selection["status"] == "selected" and operation is None:
        raise SelectionContractError("Selected plan requires an operation")
    if selection["status"] != "selected" and operation is not None:
        raise SelectionContractError("Uncertain plan must not specify an operation")

    if response["modifiers"] != []:
        raise SelectionContractError("Phase 1 does not allow modifiers")

    target = response["target"]
    if selection["status"] != "selected":
        if target is not None:
            raise SelectionContractError("Uncertain plan must not specify a target")
    else:
        if not isinstance(target, dict) or set(target) != TARGET_FIELDS:
            raise SelectionContractError("Selected plan requires a structured target")
        cid = target["candidate_id"]
        kind = target["kind"]
        index = target["node_index"]
        if not isinstance(cid, str) or cid not in selection["selected_candidate_ids"]:
            raise SelectionContractError("Target must reference a selected candidate ID")
        if kind not in ("node", "property"):
            raise SelectionContractError("Target kind must be node or property")
        record = prepared["registry"][cid]
        nodes = record.get("node_uris")
        if not isinstance(nodes, list) or not nodes:
            raise SelectionContractError("Candidate has no verified nodes")
        if type(index) is not int or index < 0 or index >= len(nodes):
            raise SelectionContractError("Target node_index is outside verified path")
        if kind == "property":
            if index != len(nodes) - 1 or not isinstance(record.get("property"), dict):
                raise SelectionContractError("Property target must be verified terminal property")
        if operation == "RETRIEVE" and kind != "property":
            raise SelectionContractError("Phase 1 RETRIEVE supports terminal properties only")
        if operation in ("COUNT", "EXISTS") and kind != "node":
            raise SelectionContractError("COUNT and EXISTS require a node target")

    return {
        **selection,
        "operation": operation,
        "target": None if target is None else {
            "candidate_id": target["candidate_id"],
            "node_index": target["node_index"],
            "kind": target["kind"],
        },
        "modifiers": [],
    }
