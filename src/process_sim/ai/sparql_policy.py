"""Conservative, fail-closed gate for generated SPARQL SELECT.

Requires rdflib grammar parsing; deploy GraphDB with read-only credentials.
"""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(?:SERVICE|FROM|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD|INSERT|DELETE|WITH|USING)\b",
    re.I,
)

def validate_select(query: str, *, max_chars: int = 8000, max_limit: int = 200) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > max_chars:
        raise ValueError("Invalid SPARQL query length")
    try:
        from rdflib.plugins.sparql.parser import parseQuery
    except ImportError as exc:
        raise RuntimeError("rdflib is required for SPARQL validation; fail closed") from exc
    try:
        parsed = parseQuery(query)
    except Exception as exc:
        raise ValueError("Invalid SPARQL syntax") from exc
    if getattr(parsed[1], "name", "") != "SelectQuery":
        raise ValueError("Only SELECT queries are permitted")
    # Strip string literals, IRI references and comments before scanning keywords.
    cleaned = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", query)
    cleaned = re.sub(r"<[^>]*>", " ", cleaned)
    cleaned = re.sub(r"#[^\n]*", " ", cleaned)
    if FORBIDDEN.search(cleaned):
        raise ValueError("Forbidden SPARQL operation or federation feature")
    limits = re.findall(r"\bLIMIT\s+(\d+)\b", cleaned, re.I)
    if len(limits) != 1 or not 1 <= int(limits[0]) <= max_limit:
        raise ValueError("Exactly one bounded LIMIT is required")
    return query
