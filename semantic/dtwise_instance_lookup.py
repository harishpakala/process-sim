"""Deterministic, unexecuted RDF instance lookup plans from SHACL identity paths.

These queries identify possible entity nodes only. A matching label never
establishes a relationship to another node.
"""
import json
import re
from urllib.parse import urlsplit


def _iri(value):
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise ValueError("Invalid predicate IRI")
    parsed = urlsplit(value)
    if not parsed.netloc or any(c in value for c in '<>"{}|^\\\\\x00\n\r\t '):
        raise ValueError("Unsafe predicate IRI")
    return "<" + value + ">"


def _lookup_values(text):
    if not isinstance(text, str) or not text.strip():
        return []
    value = " ".join(text.split())
    values = [value]
    without_article = re.sub(r"^(?:the|a|an)\\s+", "", value, flags=re.I)
    if without_article != value:
        values.append(without_article)
    return values


def plan_instance_lookups(role, candidates, limit=20):
    """Build bounded, evidence-traceable queries; do not execute them.

    Every predicate is taken from a complete SHACL property chain. The
    penultimate node is the candidate entity and the terminal predicate
    is its identity/label property. Literal comparisons are case-insensitive
    exact matches, not fuzzy or identifier-equality joins.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Invalid lookup limit")
    values = _lookup_values(role.get("text"))
    if not values:
        return []
    result, seen = [], set()
    for candidate in candidates:
        chain = candidate.get("property_chain")
        if (candidate.get("status") != "unresolved_instance_candidate"
                or not isinstance(chain, list) or not chain):
            continue
        try:
            predicates = [_iri(p) for p in chain]
        except ValueError:
            continue
        key = tuple(chain)
        if key in seen:
            continue
        seen.add(key)
        triples = []
        for i, predicate in enumerate(predicates):
            source = "?root" if i == 0 else "?node" + str(i)
            destination = "?identity" if i == len(chain) - 1 else "?node" + str(i + 1)
            triples.append("  " + source + " " + predicate + " " + destination + " .")
        entity = "?root" if len(chain) == 1 else "?node" + str(len(chain) - 1)
        alternatives = ", ".join(json.dumps(v.casefold(), ensure_ascii=True) for v in values)
        triples.append("  FILTER(LCASE(STR(?identity)) IN (" + alternatives + "))")
        query = ("SELECT DISTINCT " + entity + " ?identity WHERE {\\n"
                 + "\\n".join(triples) + "\\n} LIMIT " + str(limit))
        result.append({
            "domain": candidate.get("domain"),
            "identity_property": chain[-1],
            "property_chain": list(chain),
            "start_shape": candidate.get("start_shape"),
            "status": "unexecuted_instance_lookup",
            "sparql": query,
        })
    return result
