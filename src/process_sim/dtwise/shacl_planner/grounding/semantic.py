"""Experimental single-domain semantic search over verified SHACL schema terms.

Ranks property and shape names with Ollama nomic-embed-text. Results are
suggestions only: similarity never creates SHACL edges or selects a path.
"""
from __future__ import annotations

import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from process_sim.dtwise.shacl_planner.grounding.subgraph import _short

def schema_terms(index) -> list[dict]:
    """Only terms backed by the selected domain's indexed SHACL shapes/paths."""
    terms = []
    for uri, concept in sorted(index.shapes.items()):
        labels = [s for s in concept.get("labels", [])
                  if "shacl shape" not in s.casefold()]
        if labels:
            terms.append({"kind": "shape", "label": labels[0], "uri": uri,
                          "description": " ".join(concept.get("descriptions", []))})
    seen = set()
    for owner, properties in sorted(index.properties.items()):
        for prop in properties:
            key = (owner, prop["predicate"], prop["property_shape"])
            if key in seen:
                continue
            seen.add(key)
            terms.append({
                "kind": "property", "label": prop["name"],
                "uri": prop["property_shape"], "owner": owner,
                "predicate": prop["predicate"],
                "description": _short(prop["predicate"]),
            })
    return terms


def ollama_embed(texts: list[str], *, model: str = "nomic-embed-text:latest",
                 endpoint: str = "http://127.0.0.1:11434",
                 timeout: float = 120, transport=None) -> list[list[float]]:
    """Use local Ollama /api/embed; transport can be mocked for tests."""
    if not texts:
        return []
    payload = {"model": model, "input": texts}
    if transport is None:
        def transport(url, payload, timeout):
            request = Request(url, data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"},
                              method="POST")
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
    try:
        response = transport(endpoint.rstrip("/") + "/api/embed", payload, timeout)
        vectors = response["embeddings"]
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("Local Ollama embeddings unavailable") from exc
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Invalid Ollama embedding response") from exc
    if len(vectors) != len(texts) or not vectors or not all(
        isinstance(v, list) and v and len(v) == len(vectors[0])
        and all(isinstance(x, (float, int)) and math.isfinite(x) for x in v)
        for v in vectors
    ):
        raise ValueError("Malformed Ollama embedding vectors")
    return vectors


def semantic_terms(index, question: str, *, top_k: int = 8,
                   model: str = "nomic-embed-text:latest",
                   endpoint: str = "http://127.0.0.1:11434",
                   transport=None) -> dict:
    """Rank domain-local schema terms; do not alter extraction or select paths."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    terms = schema_terms(index)
    if not terms:
        return {"domain": index.domain, "question": question, "matches": []}
    texts = [question] + [
        (f"{t['kind']} {t['label']}. {t['description']}")
        for t in terms
    ]
    vectors = ollama_embed(texts, model=model, endpoint=endpoint,
                           transport=transport)
    query = vectors[0]
    def cosine(a, b):
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b) if norm_a and norm_b else 0.0
    matches = [{**term, "score": round(cosine(query, vec), 4)}
               for term, vec in zip(terms, vectors[1:])]
    matches.sort(key=lambda item: (-item["score"], item["kind"],
                                   item["label"], item["uri"]))
    return {"domain": index.domain, "question": question,
            "model": model, "matches": matches[:top_k]}


def semantic_grouped(index, question: str, *, top_k: int = 8,
                     model: str = "nomic-embed-text:latest",
                     endpoint: str = "http://127.0.0.1:11434",
                     transport=None) -> dict:
    """Rank shapes and properties independently; group labels, preserve members.

    top_k applies separately to unique shape labels and property labels.
    Each group retains every original SHACL term, URI, owner and predicate.
    No similarity threshold is treated as proof of semantic equivalence.
    """
    if top_k < 1:
        raise ValueError("top_k must be positive")
    terms = schema_terms(index)
    if not terms:
        return {"domain": index.domain, "question": question, "model": model,
                "shapes": [], "properties": []}
    # Embed one representative per (kind, label) so duplicated schema owners
    # do not consume retrieval slots or produce redundant embedding requests.
    grouped = {}
    for term in terms:
        key = (term["kind"], term["label"].casefold())
        grouped.setdefault(key, []).append(term)
    keys = sorted(grouped)
    texts = [question] + [
        f"{kind} {grouped[(kind, label)][0]['label']}. "
        + grouped[(kind, label)][0]["description"]
        for kind, label in keys
    ]
    vectors = ollama_embed(texts, model=model, endpoint=endpoint,
                           transport=transport)
    query = vectors[0]

    def cosine(a, b):
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b) if norm_a and norm_b else 0.0

    ranked = {"shape": [], "property": []}
    for key, vector in zip(keys, vectors[1:]):
        kind, _ = key
        members = grouped[key]
        ranked[kind].append({
            "label": members[0]["label"],
            "score": round(cosine(query, vector), 4),
            "members": members,
        })
    for groups in ranked.values():
        groups.sort(key=lambda group: (-group["score"], group["label"].casefold()))
    return {"domain": index.domain, "question": question, "model": model,
            "shapes": ranked["shape"][:top_k],
            "properties": ranked["property"][:top_k]}
