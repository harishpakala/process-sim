"""Read-only one-hop GraphDB expansion from discovered XMEAS7 subjects.

Expansion supplies candidates for human review, never authorization.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .graphdb_discovery import query_graphdb

ALLOWED_PREDICATE_PREFIXES = (
    "https://example.org/",
    "http://org.example.com/",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
)


def _sparql_iri(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Subject must be an IRI")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Subject must be an absolute HTTP(S) IRI")
    if any(ch in value for ch in '<>"{}|^\\\n\r\t '):
        raise ValueError("Unsafe IRI in discovery evidence")
    return "<" + value + ">"


def expansion_query(subjects: list[str], limit: int = 2000) -> str:
    if not subjects:
        raise ValueError("No discovery subjects")
    if len(subjects) > 100:
        raise ValueError("Too many discovery subjects")
    if not 1 <= limit <= 10000:
        raise ValueError("Invalid query limit")
    values = " ".join(_sparql_iri(subject) for subject in sorted(set(subjects)))
    return """
SELECT DISTINCT ?s ?p ?o ?g WHERE {
  VALUES ?seed { %s }
  GRAPH ?g {
    { BIND(?seed AS ?s) ?s ?p ?o }
    UNION
    { ?s ?p ?seed BIND(?seed AS ?o) }
  }
} LIMIT %d
""" % (values, limit)


def expand_discovery(discovery: dict, endpoint: str | None = None,
                     query_fn=query_graphdb) -> dict:
    if discovery.get("signal") != "XMEAS7" or discovery.get("status") != "DISCOVERY_ONLY":
        raise ValueError("Expected XMEAS7 discovery JSON")
    endpoint = endpoint or discovery["source"]
    subjects = sorted({
        row["s"] for rows in discovery["facts"].values() for row in rows
    })
    if not subjects:
        return {"signal": "XMEAS7", "status": "NO_SEEDS",
                "engineeringCertification": "U", "authorization": False,
                "facts": [], "seedSubjects": [], "truncated": False}
    rows = query_fn(endpoint, expansion_query(subjects))
    if not isinstance(rows, list):
        raise ValueError("Invalid GraphDB response")
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) for key in ("s", "p", "o", "g")
        ):
            raise ValueError("Incomplete SPARQL binding")
    return {
        "signal": "XMEAS7", "status": "EXPANDED_DISCOVERY_ONLY",
        "engineeringCertification": "U", "authorization": False,
        "source": endpoint, "seedSubjects": subjects,
        "truncated": len(rows) >= 2000,
        "facts": rows,
        "limitations": [
            "One-hop triples do not establish an authoritative multi-domain identity chain.",
            "Source graph URIs are provenance hints, not revision or authenticity proof.",
            "Missing matches may require additional explicit reference traversal.",
            "No evidence is promoted to an authorized SELiRA snapshot.",
        ],
    }
