"""Read-only cross-domain identifier search; no engineering certification."""
from __future__ import annotations

from .graphdb_discovery import DOMAINS, query_graphdb

IDENTIFIERS = ("PI_101", "PI-1101", "I10.19")
LIMIT = 2000


def build_query(identifiers=IDENTIFIERS, limit=LIMIT):
    if not identifiers or len(identifiers) > 20 or not 1 <= limit <= 10000:
        raise ValueError("Invalid search parameters")
    import json
    for identifier in identifiers:
        if not isinstance(identifier, str) or not identifier or len(identifier) > 100:
            raise ValueError("Invalid identifier")
    # SPARQL string literals are JSON-compatible for these ASCII identifiers.
    clauses = []
    for identifier in identifiers:
        literal = json.dumps(identifier.lower())
        clauses.extend([
            'CONTAINS(LCASE(STR(?s)), %s)' % literal,
            'CONTAINS(LCASE(STR(?o)), %s)' % literal,
        ])
    return """
SELECT DISTINCT ?s ?p ?o ?g WHERE {
  GRAPH ?g { ?s ?p ?o }
  FILTER(%s)
} LIMIT %d
""" % (" || ".join(clauses), limit)


def search_correspondence(endpoint, query_fn=query_graphdb,
                          identifiers=IDENTIFIERS):
    rows = query_fn(endpoint, build_query(identifiers))
    if not isinstance(rows, list):
        raise ValueError("Invalid SPARQL response")
    grouped = {domain: [] for domain in DOMAINS}
    grouped["other"] = []
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(k), str) for k in ("s", "p", "o", "g")
        ):
            raise ValueError("Incomplete SPARQL binding")
        # Classify by predicate namespace, then graph name as a fallback hint.
        domain = next((d for d in DOMAINS
                       if row["p"].startswith("https://example.org/" + d + "/")),
                      "other")
        grouped[domain].append(row)
    return {
        "identifiers": list(identifiers),
        "status": "CROSS_DOMAIN_DISCOVERY_ONLY",
        "engineeringCertification": "U",
        "authorization": False,
        "source": endpoint,
        "truncated": len(rows) >= LIMIT,
        "counts": {key: len(value) for key, value in grouped.items()},
        "facts": grouped,
        "limitations": [
            "Substring matches are not authoritative engineering identity assertions.",
            "Domain grouping uses predicate namespaces; generic AAS predicates appear under other.",
            "Missing identifiers may be represented by alternate tags or indirect relationships.",
            "No units, revision validity, live binding, or consumer authorization is established.",
        ],
    }
