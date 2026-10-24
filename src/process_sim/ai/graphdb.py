"""Bounded, read-only GraphDB schema discovery and SPARQL execution."""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA_QUERY = """
SELECT ?graph ?predicate (COUNT(*) AS ?count)
WHERE {
  GRAPH ?graph { ?subject ?predicate ?object }
}
GROUP BY ?graph ?predicate
ORDER BY DESC(?count)
LIMIT 120
"""

def select(endpoint: str, query: str, *, transport=None, timeout: int = 20) -> dict:
    """Execute a query against the configured server-side endpoint."""
    data = urlencode({"query": query}).encode("utf-8")
    if transport is None:
        def transport(request, timeout):
            with urlopen(request, timeout=timeout) as response:
                return response.read(2_000_001)
    request = Request(endpoint, data=data, method="POST", headers={
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    raw = transport(request, timeout)
    if len(raw) > 2_000_000:
        raise ValueError("GraphDB response exceeds 2 MB")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("results", {}).get("bindings"), list):
        raise ValueError("Unexpected GraphDB SELECT response")
    return parsed

def discover_schema(endpoint: str, *, transport=None) -> dict:
    """Return observed named-graph predicates, not assumed ontology assertions."""
    rows = select(endpoint, SCHEMA_QUERY, transport=transport)["results"]["bindings"]
    observed = []
    for row in rows:
        graph = row.get("graph", {}).get("value")
        predicate = row.get("predicate", {}).get("value")
        if graph and predicate:
            observed.append({"graph": graph, "predicate": predicate,
                             "count": row.get("count", {}).get("value")})
    return {"observedPredicates": observed, "truncated": len(rows) == 120,
            "note": "Observed predicates are not formal ontology domain/range constraints."}
