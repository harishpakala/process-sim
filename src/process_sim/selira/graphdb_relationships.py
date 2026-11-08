"""Bounded, read-only traversal of engineering correspondence candidates.

The result is diagnostic RDF evidence, not a certified identity path.
"""

# Created: 2026-10-30
# Author: Harish
from __future__ import annotations

from urllib.parse import urlsplit

from .graphdb_discovery import query_graphdb

MAX_SEEDS = 40
LIMIT = 2000


def _iri(value):
    if not isinstance(value, str):
        raise ValueError("Expected RDF IRI string")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Only absolute HTTP(S) RDF subject IRIs are supported")
    if any(ch in value for ch in '<>"{}|^\\\r\n\t '):
        raise ValueError("Unsafe RDF IRI")
    return "<" + value + ">"


def extract_seeds(report):
    if report.get("status") != "CROSS_DOMAIN_DISCOVERY_ONLY":
        raise ValueError("Expected cross-domain discovery report")
    facts = report.get("facts")
    if not isinstance(facts, dict):
        raise ValueError("Missing discovery facts")
    # AAS value-property subjects are leaf nodes. Use the domain-specific
    # identifier-bearing entities as roots instead.
    domains = ("dexpi", "ecad", "engineeringbom", "assetinventory", "opcuaconnectivity")
    seeds = set()
    for domain in domains:
        for row in facts.get(domain, []):
            if not isinstance(row, dict) or "s" not in row:
                raise ValueError("Invalid seed row")
            seeds.add(row["s"])
    if len(seeds) > MAX_SEEDS:
        raise ValueError("Too many seed entities")
    for seed in seeds:
        _iri(seed)
    return sorted(seeds)


def neighborhood_query(seeds, limit=LIMIT):
    if not seeds or len(seeds) > MAX_SEEDS or not 1 <= limit <= 10000:
        raise ValueError("Invalid traversal parameters")
    values = " ".join(_iri(seed) for seed in sorted(set(seeds)))
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


def _validate(rows):
    if not isinstance(rows, list):
        raise ValueError("Unexpected GraphDB response")
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) for key in ("s", "p", "o", "g")
        ):
            raise ValueError("Incomplete GraphDB binding")
    return rows


def traverse_correspondence(report, endpoint=None, query_fn=query_graphdb):
    seeds = extract_seeds(report)
    endpoint = endpoint or report["source"]
    if not seeds:
        return {
            "status": "NO_SEEDS", "engineeringCertification": "U",
            "authorization": False, "seedSubjects": [], "facts": [],
            "truncated": False,
        }
    # Stage 1: complete direct descriptions of each engineering entity.
    direct = _validate(query_fn(endpoint, neighborhood_query(seeds)))
    # Stage 2: inspect descriptions of IRI neighbors, excluding vocabulary
    # objects and previously visited seeds. This is a bounded second hop.
    neighbors = sorted({
        value for row in direct for value in (row["s"], row["o"])
        if isinstance(value, str)
        and value.startswith(("http://org.example.com/", "https://aas.example.com/"))
        and value not in seeds
    })
    limited_neighbors = neighbors[:MAX_SEEDS]
    linked = (_validate(query_fn(endpoint, neighborhood_query(limited_neighbors)))
              if limited_neighbors else [])
    # Preserve named graph, deduplicating exact matching quadruples.
    seen = set()
    facts = []
    for row in direct + linked:
        key = (row["s"], row["p"], row["o"], row["g"])
        if key not in seen:
            seen.add(key)
            facts.append(row)
    return {
        "status": "RELATIONSHIP_DISCOVERY_ONLY",
        "engineeringCertification": "U",
        "authorization": False,
        "source": endpoint,
        "seedSubjects": seeds,
        "linkedSubjects": limited_neighbors,
        "truncated": len(direct) >= LIMIT or len(linked) >= LIMIT
                     or len(neighbors) > MAX_SEEDS,
        "directCount": len(direct),
        "linkedCount": len(linked),
        "facts": facts,
        "limitations": [
            "Traversal is bounded to two hops; omitted neighbors or result limits may hide evidence.",
            "Shared literal identifiers are not proof of explicit cross-domain identity.",
            "RDF graph membership is not revision approval or provenance authentication.",
            "No quantity/unit or live OPC UA binding certification is performed.",
            "No SELiRA authorization or validated evidence snapshot is produced.",
        ],
    }
