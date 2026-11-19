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
    required = {
        "path_id", "operation", "projections", "group_by", "count_target",
        "aggregate_condition", "filters",
    }
    optional = {"where", "order_by", "limit", "distinct", "optional_properties"}
    if (not isinstance(selection, dict) or not required.issubset(selection)
            or set(selection) - required - optional):
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
                or not isinstance(f["property"], str)
                or f["property"] not in property_ids
                or f["op"] not in ("eq", "contains")
                or not isinstance(f["value"], str)
                or len(f["value"]) > 1000):
            raise ValueError("Invalid evidenced property filter")
    # Optional v2 features use explicit, evidence-bound structure rather than
    # interpreting benchmark wording or silently inserting constraints.
    optional_properties = selection.get("optional_properties", [])
    if (not isinstance(optional_properties, list)
            or not all(isinstance(p, str) and p in property_ids
                       for p in optional_properties)
            or len(optional_properties) != len(set(optional_properties))
            or any(p not in projections for p in optional_properties)
            or (operation != "select" and optional_properties)):
        raise ValueError("Invalid optional projection evidence IDs")

    def validate_where(node, depth=0):
        if depth > 8 or not isinstance(node, dict):
            raise ValueError("Invalid Boolean condition")
        op = node.get("op")
        if op in ("and", "or"):
            children = node.get("conditions")
            if (set(node) != {"op", "conditions"}
                    or not isinstance(children, list)
                    or not 2 <= len(children) <= 16):
                raise ValueError("Invalid Boolean condition")
            return {"op": op, "conditions": [
                validate_where(child, depth + 1) for child in children]}
        if op == "not":
            if set(node) != {"op", "condition"}:
                raise ValueError("Invalid Boolean condition")
            return {"op": op, "condition": validate_where(
                node["condition"], depth + 1)}
        if op in ("exists", "missing"):
            if (set(node) != {"op", "property"}
                    or not isinstance(node["property"], str)
                    or node["property"] not in property_ids):
                raise ValueError("Invalid property existence condition")
            return {"op": op, "property": node["property"]}
        if op in ("eq", "contains", "starts_with", "regex"):
            if (set(node) not in ({"op", "property", "value"},
                                  {"op", "property", "value", "ignore_case"})
                    or not isinstance(node["property"], str)
                    or node["property"] not in property_ids
                    or not isinstance(node["value"], str)
                    or len(node["value"]) > 1000
                    or not isinstance(node.get("ignore_case", False), bool)
                    or (op == "eq" and "ignore_case" in node)):
                raise ValueError("Invalid literal condition")
            if op == "regex":
                import re
                if len(node["value"]) > 256:
                    raise ValueError("Invalid regex condition")
                try:
                    re.compile(node["value"])
                except re.error as exc:
                    raise ValueError("Invalid regex condition") from exc
            return dict(node)
        raise ValueError("Unsupported Boolean condition operator")

    where = selection.get("where")
    if where is not None:
        where = validate_where(where)
    if filters and where is not None:
        raise ValueError("Use either legacy filters or Boolean where, not both")
    order_by = selection.get("order_by")
    if order_by is not None:
        if (not isinstance(order_by, dict)
                or set(order_by) != {"property", "direction"}
                or not isinstance(order_by["property"], str)
                or order_by["property"] not in property_ids
                or order_by["direction"] not in ("asc", "desc")
                or operation != "select"):
            raise ValueError("Invalid ordering specification")
    limit = selection.get("limit")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 10000
                              or operation != "select"):
        raise ValueError("Invalid result limit")
    distinct = selection.get("distinct", False)
    if not isinstance(distinct, bool):
        raise ValueError("Invalid distinct flag")
    if operation == "group_count" and distinct:
        raise ValueError("Distinct count requires explicit count-target semantics")
    return {
        "path_id": path_id, "operation": operation,
        "projections": list(projections), "group_by": list(group_by),
        "count_target": target,
        "aggregate_condition": dict(condition) if condition is not None else None,
        "filters": [dict(f) for f in filters],
        **({"where": where} if "where" in selection else {}),
        **({"order_by": dict(order_by) if order_by else None}
           if "order_by" in selection else {}),
        **({"limit": limit} if "limit" in selection else {}),
        **({"distinct": distinct} if "distinct" in selection else {}),
        **({"optional_properties": list(optional_properties)}
           if "optional_properties" in selection else {}),
    }
