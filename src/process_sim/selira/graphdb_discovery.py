"""Read-only GraphDB engineering evidence discovery for SELiRA.

Discovery is NOT certification: these triples are candidate facts, not a
reviewed revision-scoped engineering identity chain. Never generate a
validated declaration from this module.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

DOMAINS = ("dexpi", "ecad", "opcuaconnectivity", "assetinventory", "engineeringbom")
PREFIXES = tuple("https://example.org/" + d + "/" for d in DOMAINS)
QUERY = """
SELECT DISTINCT ?s ?p ?o ?g WHERE {
  GRAPH ?g { ?s ?p ?o }
  FILTER(
    STRSTARTS(STR(?p), "https://example.org/dexpi/") ||
    STRSTARTS(STR(?p), "https://example.org/ecad/") ||
    STRSTARTS(STR(?p), "https://example.org/opcuaconnectivity/") ||
    STRSTARTS(STR(?p), "https://example.org/assetinventory/") ||
    STRSTARTS(STR(?p), "https://example.org/engineeringbom/")
  )
  FILTER(
    CONTAINS(LCASE(STR(?s)), "xmeas7") ||
    CONTAINS(LCASE(STR(?o)), "xmeas7") ||
    CONTAINS(LCASE(STR(?s)), "xmeas(7)") ||
    CONTAINS(LCASE(STR(?o)), "xmeas(7)") ||
    CONTAINS(LCASE(STR(?s)), "xmeas_7") ||
    CONTAINS(LCASE(STR(?o)), "xmeas_7")
  )
} LIMIT 500
"""


def query_graphdb(endpoint: str, query: str = QUERY):
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("GraphDB endpoint must be an HTTP(S) URL")
    body = urllib.parse.urlencode({"query": query}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    return [{k: v["value"] for k, v in binding.items()}
            for binding in result["results"]["bindings"]]


def inspect_xmeas7(endpoint: str, query_fn=query_graphdb):
    """Inventory matching facts, preserving duplicates and source graph URIs."""
    rows = query_fn(endpoint)
    if not isinstance(rows, list):
        raise ValueError("Unexpected GraphDB response")
    by_domain = {d: [] for d in DOMAINS}
    for row in rows:
        if not isinstance(row, dict) or not all(k in row for k in ("s", "p", "o", "g")):
            raise ValueError("Incomplete SPARQL binding")
        for domain in DOMAINS:
            if row["p"].startswith("https://example.org/" + domain + "/"):
                by_domain[domain].append(row)
                break
    return {
        "signal": "XMEAS7",
        "status": "DISCOVERY_ONLY",
        "engineeringCertification": "U",
        "authorization": False,
        "source": endpoint,
        "truncated": len(rows) >= 500,
        "counts": {domain: len(items) for domain, items in by_domain.items()},
        "facts": by_domain,
        "limitations": [
            "Matching triples do not prove an authoritative DEXPI-ECAD-PLC-OPCUA identity chain.",
            "No revision, quantity-kind, or unit authenticity is established.",
            "A zero result can mean absent mappings, differing identifiers, or dataset visibility issues.",
            "No reviewed evidence snapshot is generated or authorized.",
        ],
    }
