"""Fail-closed policy gate for model-generated SPARQL.

Requires rdflib for real SPARQL grammar parsing. This is a prototype gate,
not a replacement for GraphDB read-only credentials and query limits.
"""
from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\\b(?:SERVICE|FROM|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD|INSERT|DELETE|WITH|USING)\\b",
    re.IGNORECASE,
)

def validate_select(query: str, *, max_chars: int = 8000, max_limit: int = 200) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > max_chars:
        raise ValueError("Invalid SPARQL query length")
    try:
        from rdflib.plugins.sparql.parser import parseQuery
    except ImportError as exc:
        raise RuntimeError("rdflib is required for SPARQL validation; fail closed") from exc
    # Parse before evaluating query kind; lexical checks alone are insufficient.
    try:
        parsed = parseQuery(query)
    except Exception as exc:
        raise ValueError("Invalid SPARQL syntax") from exc
    kind = getattr(parsed[1], "name", "")
    if kind != "SelectQuery":
        raise ValueError("Only SELECT queries are permitted")
    # Conservative token scan with comments and quoted literals removed.
    cleaned = re.sub(r'"""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\'|"(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\'', ' ', query)
    cleaned = re.sub(r"#[^\\n]*", " ", cleaned)
    if FORBIDDEN.search(cleaned):
        raise ValueError("Forbidden SPARQL operation or federation feature")
    # LIMIT is mandatory; no implicit unlimited graph traversal.
    limits = re.findall(r"\\bLIMIT\\s+(\\d+)\\b", cleaned, re.I)
    if len(limits) != 1 or not 1 <= int(limits[0]) <= max_limit:
        raise ValueError("Exactly one bounded LIMIT is required")
    return query
