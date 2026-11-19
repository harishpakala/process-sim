"""Evidence-bound semantic selection contract (v2).

This is a planner-facing contract, not a replacement for unified IR 1.0.
The LLM chooses identifiers; validation only checks structure and membership.
"""
from __future__ import annotations

from typing import Any


def validate_semantic_selection_v2(
    selection: Any, *, path_ids: set[str], property_ids: set[str],
    entity_ids: set[str],
) -> dict:
    """Validate a proposed LLM selection without guessing missing semantics.

    Property/entity IDs must be supplied by the evidence catalog for the
    selected path. Callers must not pass IDs from unrelated candidate paths.
    """
    if not isinstance(selection, dict) or set(selection) != {
        "path_id", "operation", "projections", "group_by", "count_target",
        "aggregate_condition", "filters",
    }:
        raise ValueError("Invalid semantic selection v2 structure")
    path_id = selection["path_id"]
    if not isinstance(path_id, str) or path_id not in path_ids:
        raise ValueError("Missing or invalid evidence path ID")
    operation = selection["operation"]
    if operation not in ("select", "count", "group_count"):
        raise ValueError("Unsupported semantic selection operation")
    projections = selection["projections"]
    group_by = selection["group_by"]
    if not isinstance(projections, list) or not all(
        isinstance(p, str) and p in property_ids for p in projections
    ) or len(projections) != len(set(projections)):
        raise ValueError("Invalid projection evidence IDs")
    if not isinstance(group_by, list) or not all(
        isinstance(p, str) and p in property_ids for p in group_by
    ) or len(group_by) != len(set(group_by)):
        raise ValueError("Invalid grouping evidence IDs")
    target = selection["count_target"]
    condition = selection["aggregate_condition"]
    if operation == "select":
        if group_by or target is not None or condition is not None:
            raise ValueError("SELECT cannot carry aggregate semantics")
    elif operation == "count":
        if projections or group_by or target not in entity_ids or condition is not None:
            raise ValueError("COUNT requires a counted entity without grouping")
    else:
        if (len(group_by) != 1 or projections != group_by
                or target not in entity_ids):
            raise ValueError("GROUP_COUNT requires one evidenced grouping key and count target")
        if condition is not None:
            if (not isinstance(condition, dict)
                    or set(condition) != {"operator", "value"}
                    or condition["operator"] not in ("gt", "gte", "eq", "lt", "lte")
                    or type(condition["value"]) is not int
                    or not 0 <= condition["value"] <= 1000000):
                raise ValueError("Invalid aggregate condition")
    filters = selection["filters"]
    if not isinstance(filters, list) or len(filters) > 16:
        raise ValueError("Invalid semantic filters")
    for f in filters:
        if (not isinstance(f, dict) or set(f) != {"property", "op", "value"}
                or f["property"] not in property_ids
                or f["op"] not in ("eq", "contains")
                or not isinstance(f["value"], str)
                or len(f["value"]) > 1000):
            raise ValueError("Invalid evidenced property filter")
    return {
        "path_id": path_id, "operation": operation,
        "projections": list(projections), "group_by": list(group_by),
        "count_target": target,
        "aggregate_condition": dict(condition) if condition is not None else None,
        "filters": [dict(f) for f in filters],
    }
