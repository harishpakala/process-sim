"""Deterministic query-structure routing; SHACL validation stays in each operation.

This classifier does not call Ollama, identify shapes, or generate SPARQL.
Unrecognized structures abstain rather than selecting an arbitrary operation.
"""
from __future__ import annotations

import re

OPERATIONS = (
    "phase1-plan", "phase2-filter", "phase3-and", "phase4-join",
    "phase4-filtered-join", "phase4-and-join", "direct-intent",
)

_UNSUPPORTED = re.compile(
    r"\b(?:how many|count|average|sum|group by|order by|sort|minimum|maximum|"
    r"greater than|less than|not equal|exclude|without)\b|!=|<=|>=|(?<![=<>])(?:<|>)(?![=])",
    re.I,
)
_EQUALITY = re.compile(r"\b([A-Za-z][\w.]*)\s*=\s*([^\s,;]+)", re.I)
_NATURAL_FILTER = re.compile(
    r"\b(?:with|having)\s+([A-Za-z][\w.]*)\s+([A-Za-z0-9_]+)"
    r"(?:\s+and\s+([A-Za-z][\w.]*)\s+([A-Za-z0-9_]+))?", re.I,
)


def extract_query_structure(question: str) -> dict | None:
    """Extract only syntactic signals, without schema-specific identifiers.

    An explicit conjunction of requested result branches is different from
    ordinary path traversal ('Address of EndPoint belonging to Device').
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty")
    q = question.strip()
    if _UNSUPPORTED.search(q):
        return {"unsupported": True, "reason": "Unsupported query operator or action"}
    # Filters can be introduced with 'where' or with a natural-language
    # 'with Property Value' clause. Never treat conjunctions in the result
    # phrase as Boolean filter operators.
    where = re.search(r"\bwhere\b", q, re.I)
    natural = _NATURAL_FILTER.search(q) if not where else None
    if where:
        head, clause = q[:where.start()], q[where.end():]
        explicit = True
        filters = _EQUALITY.findall(clause)
        if not filters or re.search(r"\b(?:and|or)\b", clause, re.I) and len(filters) < 2:
            return None
    elif natural:
        head, clause = q[:natural.start()], q[natural.start():]
        explicit = False
        filters = [(natural.group(1), natural.group(2))]
        if natural.group(3):
            filters.append((natural.group(3), natural.group(4)))
    else:
        head, clause, filters, explicit = q, "", [], False
    # Requested sibling branches must be explicit in the result phrase.
    # 'A and B belonging to the same Owner' and 'addresses of A and B for
    # owners ...' qualify as structural sibling requests; the operation
    # itself verifies whether the SHACL graph actually supports the join.
    sibling = bool(re.search(r"\b(?:and|&)\b", head, re.I) and
                   re.search(r"\b(?:same|belonging to|for|of)\b", head, re.I))
    logic_tokens = re.findall(r"\b(and|or)\b", clause, re.I)
    logic = {token.upper() for token in logic_tokens}
    boolean = "MIXED" if len(logic) > 1 else next(iter(logic), None)
    return {"unsupported": False, "sibling": sibling, "filters": filters,
            "boolean_operator": boolean, "explicit_filter_syntax": explicit}


def operation_from_structure(structure: dict | None) -> dict:
    unsupported = {"status": "unsupported", "operation": None,
                   "reason": "Cannot safely determine a supported query structure"}
    if structure is None:
        return unsupported
    if structure.get("unsupported"):
        return {**unsupported, "reason": structure["reason"]}
    count = len(structure["filters"])
    sibling = structure["sibling"]
    logic = structure["boolean_operator"]
    explicit = structure["explicit_filter_syntax"]
    if count > 1 and logic is None or count <= 1 and logic is not None:
        return unsupported
    if sibling:
        if count == 0:
            operation = "phase4-join"
        elif not explicit:
            operation = "direct-intent"
        elif count == 1:
            operation = "phase4-filtered-join"
        else:
            operation = "phase4-and-join"
    elif count == 0:
        operation = "phase1-plan"
    elif count == 1:
        operation = "phase2-filter"
    elif count == 2 and logic == "AND":
        operation = "phase3-and"
    else:
        return unsupported
    return {"status": "supported", "operation": operation,
            "reason": "Deterministic syntax classification; operation validates SHACL"}


def classify_single_domain_query(question: str, *, model=None,
                                 endpoint=None, transport=None) -> dict:
    """Compatibility signature; no model, transport, or network access is used."""
    structure = extract_query_structure(question)
    return {**operation_from_structure(structure), "structure": structure}
