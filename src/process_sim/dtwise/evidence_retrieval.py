"""Bounded candidate retrieval for LLM-first evidence-grounded planning.

Retrieval ranks schema labels; it never selects a query operator or produces IR.
All retrieved evidence IDs retain their globally stable catalog identity.
"""
from __future__ import annotations

import re

from .semantic_planning import EvidenceCatalog


def _tokens(value):
    # Split camel case and punctuation, including URI and URN separators.
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def retrieve_evidence(question: str, evidence: EvidenceCatalog, *,
                      max_entities: int = 16, max_properties: int = 96,
                      max_relationships: int = 48) -> EvidenceCatalog:
    """Retrieve a bounded, ownership-consistent view of a verified catalog.

    Entity and property ranking is generic lexical relevance, not deterministic
    semantic interpretation. An LLM must still choose the operation and IDs.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be nonempty")
    for limit in (max_entities, max_properties, max_relationships):
        if type(limit) is not int or limit < 1:
            raise ValueError("Retrieval limits must be positive integers")
    query = _tokens(question)
    entity_by_id = {e["id"]: e for e in evidence.entities}
    props_by_entity = {}
    for prop in evidence.properties:
        props_by_entity.setdefault(prop["entity_id"], []).append(prop)

    def score(tokens):
        shared = query & tokens
        # Favor distinctive multi-token overlap without assuming intent.
        return (len(shared), sum(len(t) for t in shared))

    def entity_score(entity):
        own = score(_tokens(entity["domain"]) | _tokens(entity["shape"]))
        related = max((score(_tokens(p["label"]) | _tokens(p["predicate"]))
                       for p in props_by_entity.get(entity["id"], [])),
                      default=(0, 0))
        return (max(own[0], related[0]), max(own[1], related[1]))

    ranked_entities = sorted(
        evidence.entities, key=lambda e: (
            -entity_score(e)[0], -entity_score(e)[1], e["id"]))
    selected_entities = ranked_entities[:max_entities]
    selected_entity_ids = {e["id"] for e in selected_entities}

    eligible_props = [p for p in evidence.properties
                      if p["entity_id"] in selected_entity_ids]
    ranked_props = sorted(eligible_props, key=lambda p: (
        -score(_tokens(p["label"]) | _tokens(p["predicate"]))[0],
        -score(_tokens(p["label"]) | _tokens(p["predicate"]))[1],
        p["id"]))
    selected_props = ranked_props[:max_properties]
    # Do not show entities with no selectable properties unless needed for
    # a relationship endpoint; their shape evidence remains valid.
    eligible_edges = [r for r in evidence.relationships
                      if r["from_entity_id"] in selected_entity_ids
                      and r["to_entity_id"] in selected_entity_ids]
    ranked_edges = sorted(eligible_edges, key=lambda r: (
        -score(_tokens(r["predicate"]))[0],
        -score(_tokens(r["predicate"]))[1], r["id"]))
    return EvidenceCatalog(tuple(selected_entities), tuple(selected_props),
                           tuple(ranked_edges[:max_relationships]))
