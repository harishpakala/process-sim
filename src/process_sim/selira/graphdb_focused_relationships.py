"""Focused read-only GraphDB inspection of XMEAS7 engineering relationships."""

# Created: 2026-10-30
# Author: Harish
from __future__ import annotations

from .graphdb_discovery import query_graphdb
from .graphdb_relationships import _iri, _validate, extract_seeds

PAGE_SIZE = 400
MAX_PAGES = 25
FOCUS = ("connected", "function", "measurement", "variable", "quantity",
         "unit", "revision", "valid", "equivalence", "association",
         "reference", "mapping", "address", "channel", "signal",
         "node", "status", "parent", "assembly", "assetidentifier",
         "localid", "equipmenttag", "basis", "source", "instrument")


def focus_query(seeds, limit=PAGE_SIZE, offset=0):
    if not seeds or not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("Invalid query arguments")
    values = " ".join(_iri(seed) for seed in sorted(set(seeds)))
    # Retrieve direct domain assertions, direct cross-entity links, and
    # values of AAS property nodes selected by their parent-relative path.
    # Explicitly exclude generic parent collection expansion.
    terms = " || ".join(
        'CONTAINS(LCASE(STR(?p)), "%s")' % term for term in FOCUS
    )
    paths = " || ".join(
        'CONTAINS(LCASE(STR(?property)), "%s")' % term for term in FOCUS
    )
    return """
SELECT DISTINCT ?s ?p ?o ?g WHERE {
  VALUES ?seed { %s }
  GRAPH ?g {
    {
      BIND(?seed AS ?s)
      ?s ?p ?o .
      FILTER(%s)
    }
    UNION
    {
      ?seed <https://example.org/aas/hasSubmodelElement> ?property .
      FILTER(%s)
      BIND(?property AS ?s)
      ?s ?p ?o .
    }
    UNION
    {
      ?s ?p ?seed .
      FILTER(%s)
      BIND(?seed AS ?o)
    }
  }
}
ORDER BY ?g ?s ?p ?o
LIMIT %d OFFSET %d
""" % (values, terms, paths, terms, limit, offset)


def focused_relationships(report, endpoint=None, query_fn=query_graphdb,
                          page_size=PAGE_SIZE, max_pages=MAX_PAGES):
    seeds = extract_seeds(report)
    endpoint = endpoint or report["source"]
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 100:
        raise ValueError("Invalid pagination limits")
    facts, seen = [], set()
    exhausted = not seeds
    pages = 0
    if seeds:
        for page in range(max_pages):
            rows = _validate(query_fn(
                endpoint, focus_query(seeds, page_size, page * page_size)))
            pages += 1
            for row in rows:
                key = tuple(row[k] for k in ("s", "p", "o", "g"))
                if key not in seen:
                    seen.add(key)
                    facts.append(row)
            if len(rows) < page_size:
                exhausted = True
                break
    return {
        "status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
        "engineeringCertification": "U",
        "authorization": False,
        "source": endpoint,
        "seedSubjects": seeds,
        "pagesFetched": pages,
        "truncated": not exhausted,
        "facts": facts,
        "limitations": [
            "Predicate/property-name focus may exclude relevant differently named relations.",
            "Pagination covers the focused result set only, not the entire knowledge graph.",
            "Literal agreement is not a certified cross-domain identity relation.",
            "No verified quantity/unit, revision, or live OPC UA binding is asserted.",
            "No consumer authorization is generated.",
        ],
    }
