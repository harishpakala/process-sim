"""Validate compiled SPARQL syntax independently of compilation and execution."""
from __future__ import annotations


def validate_syntax(sparql: str) -> dict:
    """Parse SPARQL using RDFLib; do not execute or infer semantic correctness."""
    if not isinstance(sparql, str) or not sparql.strip():
        return {"status": "missing_query", "error": "No SPARQL query supplied"}
    try:
        from rdflib.plugins.sparql.parser import parseQuery
    except ImportError as exc:
        return {"status": "dependency_missing", "error": str(exc)}
    try:
        parseQuery(sparql)
    except Exception as exc:
        return {"status": "syntax_failed",
                "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "syntax_valid", "error": None}
