"""Bounded SHACL-verified path candidates from semantic schema term suggestions.

Embedding scores retrieve vocabulary, never authorize edges, properties or joins.
Every candidate is assembled solely from the selected domain's SHACL index.
"""
from __future__ import annotations

from collections import defaultdict
from time import perf_counter

from process_sim.dtwise.experimental_shacl_semantic import semantic_grouped
from process_sim.dtwise.experimental_shacl_subgraph import _short


def semantic_candidates(index, question: str, *, top_shapes: int = 8,
                        top_properties: int = 2, max_candidates: int = 64,
                        max_depth: int = 6, transport=None,
                        endpoint: str = "http://127.0.0.1:11434",
                        model: str = "nomic-embed-text:latest", timing=None) -> dict:
    """Return normal prompt/registry candidate contract and retrieval evidence.

    Retains alternatives; never picks a branch by embedding score.
    """
    if min(top_shapes, top_properties, max_candidates, max_depth) < 1:
        raise ValueError("Budgets must be positive")
    t0 = perf_counter()
    retrieval = semantic_grouped(
        index, question, top_k=max(top_shapes, top_properties),
        model=model, endpoint=endpoint, transport=transport,
    )
    if timing is not None:
        timing["embedding_and_ranking_ms"] = (perf_counter() - t0) * 1000
    t0 = perf_counter()
    shape_groups = retrieval["shapes"][:top_shapes]
    property_groups = retrieval["properties"][:top_properties]
    shape_uris = {member["uri"] for group in shape_groups
                  for member in group["members"]}
    properties = {
        (member["owner"], member["predicate"], member["uri"])
        for group in property_groups for member in group["members"]
    }
    outgoing = defaultdict(list)
    incoming = set()
    for edge in index.edges:
        if edge["from"] in index.shapes and edge["to"] in index.shapes:
            outgoing[edge["from"]].append(edge)
            incoming.add(edge["to"])
    for edges in outgoing.values():
        edges.sort(key=lambda edge: (edge["predicate"], edge["to"]))
    roots = sorted(set(index.shapes) - incoming)
    if not roots and index.shapes:
        raise ValueError("No SHACL graph roots found")
    names = {
        uri: next((label for label in concept.get("labels", [])
                   if "shacl shape" not in label.casefold()), _short(uri))
        for uri, concept in index.shapes.items()
    }
    found = {}

    def walk(uri, nodes, edges):
        # Depth bounds traversal even if the schema contains cycles.
        if len(nodes) > max_depth:
            return
        if uri in shape_uris:
            for prop in index.properties.get(uri, []):
                key = (uri, prop["predicate"], prop["property_shape"])
                if key in properties:
                    signature = (tuple(nodes), tuple(
                        (e["from"], e["predicate"], e["to"], e["property_shape"])
                        for e in edges), key)
                    found[signature] = (nodes[:], edges[:], prop)
                    if len(found) > max_candidates:
                        raise ValueError("Semantic candidate budget exceeded")
        for edge in outgoing[uri]:
            if edge["to"] not in nodes:
                walk(edge["to"], nodes + [edge["to"]], edges + [edge])

    for root in roots:
        walk(root, [root], [])
    ordered = sorted(found.values(), key=lambda item: (
        tuple(names[uri] for uri in item[0]), tuple(item[0]),
        item[2]["predicate"], item[2]["property_shape"],
    ))
    candidates = []
    registry = {}
    for number, (nodes, edges, prop) in enumerate(ordered, 1):
        candidate_id = f"C{number}"
        candidates.append({
            "id": candidate_id,
            "path": " → ".join([*(names[uri] for uri in nodes), prop["name"]]),
        })
        registry[candidate_id] = {
            "node_uris": nodes, "edges": edges, "property": prop,
        }
    if timing is not None:
        timing["candidate_assembly_ms"] = (perf_counter() - t0) * 1000
    return {
        "prompt": {"domain": index.domain, "question": question,
                   "candidates": candidates},
        "registry": registry,
        "retrieval": {"shapes": shape_groups, "properties": property_groups},
    }
