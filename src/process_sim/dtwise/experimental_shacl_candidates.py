"""Build bounded, single-domain SHACL path candidates for a future LLM.

The prompt-facing payload contains only IDs and labels. The local registry
retains the original verified edges, property metadata and evidence.
No semantic selection, API call or SPARQL generation happens here.
"""
from __future__ import annotations

from collections import defaultdict, deque


def prepare_candidates(result: dict, max_candidates: int = 64) -> dict:
    """Return {'prompt': ..., 'registry': ...} from an extracted subgraph.

    One candidate represents one directed root-to-property-owner path.
    Disconnected properties become one-node candidates. All paths must be
    composed of edges already present in the extracted result.
    """
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    names = {node["uri"]: node["name"] for node in result["nodes"]}
    outgoing = defaultdict(list)
    incoming = set()
    for edge in result["edges"]:
        if edge["from"] not in names or edge["to"] not in names:
            raise ValueError("Edge references a node outside the extracted subgraph")
        outgoing[edge["from"]].append(edge)
        incoming.add(edge["to"])
    for edges in outgoing.values():
        edges.sort(key=lambda e: (e["predicate"], e["to"]))
    roots = sorted(set(names) - incoming)
    paths = []

    def walk(node: str, nodes: list[str], edges: list[dict]) -> None:
        if len(paths) > max_candidates:
            raise ValueError("Candidate budget exceeded")
        for prop in result["properties"]:
            if prop["owner"] == node:
                paths.append((nodes[:], edges[:], prop))
                if len(paths) > max_candidates:
                    raise ValueError("Candidate budget exceeded")
        for edge in outgoing[node]:
            target = edge["to"]
            if target in nodes:
                raise ValueError("Cycle in extracted SHACL subgraph")
            walk(target, nodes + [target], edges + [edge])

    for root in roots:
        walk(root, [root], [])
    # If the extracted graph has no roots, it is cyclic or malformed.
    if names and not roots:
        raise ValueError("No root found in extracted SHACL subgraph")
    # Keep only grounded property candidates, never add unrequested properties.
    paths.sort(key=lambda entry: (
        tuple(names[uri] for uri in entry[0]),
        tuple(entry[0]),
        entry[2]["predicate"],
        entry[2]["property_shape"],
    ))
    prompt_candidates = []
    registry = {}
    for i, (nodes, edges, prop) in enumerate(paths, 1):
        candidate_id = f"C{i}"
        prompt_candidates.append({
            "id": candidate_id,
            "path": " → ".join([*(names[uri] for uri in nodes), prop["name"]]),
        })
        registry[candidate_id] = {
            "node_uris": nodes,
            "edges": edges,
            "property": prop,
        }
    return {
        "prompt": {
            "domain": result["domain"],
            "question": result["question"],
            "candidates": prompt_candidates,
        },
        "registry": registry,
    }
