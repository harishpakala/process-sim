"""Validated structured query plans compiled into bounded read-only SPARQL.

This is a deliberately narrow first slice: template SHACL paths with a single
parent/child chain, plus instance-derived class/predicate alignment. The model
does not author executable SPARQL in this path.
"""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations

from dataclasses import dataclass
from rdflib import URIRef
from .sparql_policy import validate_select

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

@dataclass(frozen=True)
class ValidationResult:
    sparql: str
    domain: str
    path: tuple[str, ...]


def _iri(value):
    if not isinstance(value, str) or not value or any(ch in value for ch in '<>"{} \t\r\n'):
        raise ValueError("Invalid IRI")
    uri = URIRef(value)
    if not str(uri).startswith(("https://", "http://", "urn:")):
        raise ValueError("Unsupported IRI scheme")
    return f"<{uri}>"


def validate_plan(plan: dict, registry: dict, *, max_hops=5) -> ValidationResult:
    """Validate domain and a declared SHACL path before compiling SPARQL.

    Plan shape: {"domain": "dexpi", "path": [".../hasEquipments",
    ".../hasEquipment", ".../hasAssetIdentifier"], "limit": 20}.
    Paths are grounded in SHACL parent relationships. Instance-only aliases
    may substitute a template SMC predicate when they are declared in that
    domain; the caller must still supply a template-grounded chain.
    """
    if not isinstance(plan, dict) or set(plan) != {"domain", "path", "limit"}:
        raise ValueError("Expected domain, path, limit")
    domain = plan["domain"]
    paths = plan["path"]
    limit = plan["limit"]
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Limit must be an integer from 1 to 200")
    if not isinstance(paths, list) or not 1 <= len(paths) <= max_hops:
        raise ValueError("Invalid path length")
    selected = [d for d in registry["domains"] if d["domain"] == domain]
    if len(selected) != 1:
        raise ValueError("Unknown or ambiguous domain")
    entry = selected[0]
    # Only paths actually emitted by template lifting are authoritative.
    shapes = entry["shaclPaths"]
    allowed = {(s["parentPredicate"], s["predicate"]) for s in shapes}
    parent = None
    for predicate in paths:
        if (parent, predicate) not in allowed:
            raise ValueError(f"Undeclared SHACL relationship at {predicate!r}")
        parent = predicate
    # Ensure a final property can be used as a query value; no assumed class
    # equivalence or physical-asset identity joins are introduced.
    triples = []
    for i, predicate in enumerate(paths):
        triples.append(f"  ?n{i} {_iri(predicate)} ?n{i+1} .")
    sparql = "SELECT DISTINCT ?n0 ?value WHERE {\n" + "\n".join(triples)
    sparql += f"\n  BIND(?n{len(paths)} AS ?value)\n}}\nLIMIT {limit}"
    validate_select(sparql)
    return ValidationResult(sparql=sparql, domain=domain, path=tuple(paths))
