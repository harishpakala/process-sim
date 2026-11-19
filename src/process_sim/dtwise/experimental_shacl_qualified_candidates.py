"""Domain-qualified candidate view for future intent-aware planning.

This is an additive adapter: legacy semantic candidates and SPARQL compilation
remain unchanged. Only SHACL-index metadata is trusted for paths and predicates.
"""
from __future__ import annotations

from process_sim.dtwise.experimental_shacl_subgraph import _short


def qualify_candidates(index, prepared: dict) -> dict:
    """Return explicit result/property candidates with a verified internal registry.

    Existing property-ending paths become property candidates; each prefix
    becomes a result candidate. Multiple property paths may share a prefix.
    Property *use* (projection/filter/sort) is determined later by the plan.
    """
    domain = index.domain
    if prepared.get("prompt", {}).get("domain") != domain:
        raise ValueError("Prepared candidates belong to a different domain")
    old = prepared["prompt"]["candidates"]
    registry = prepared["registry"]
    if len({c["id"] for c in old}) != len(old) or {c["id"] for c in old} != set(registry):
        raise ValueError("Prepared candidate IDs and registry disagree")
    names = {
        uri: next((v for v in shape.get("labels", [])
                   if "shacl shape" not in v.casefold()), _short(uri))
        for uri, shape in index.shapes.items()
    }
    verified_edges = {
        (e["from"], e["predicate"], e["to"], e["property_shape"])
        for e in index.edges
    }
    verified_properties = {
        (p["owner"], p["predicate"], p["property_shape"])
        for props in index.properties.values() for p in props
    }
    result_paths = {}
    property_paths = {}
    for item in old:
        source = registry[item["id"]]
        nodes, edges, prop = source["node_uris"], source["edges"], source["property"]
        if not nodes or len(edges) != len(nodes) - 1:
            raise ValueError("Invalid node/edge sequence")
        if any(uri not in index.shapes for uri in nodes):
            raise ValueError("Candidate includes a shape outside active domain")
        for i, edge in enumerate(edges):
            signature = (edge["from"], edge["predicate"], edge["to"], edge["property_shape"])
            if (edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]
                    or signature not in verified_edges):
                raise ValueError("Candidate edge is not verified in active domain")
        key = (prop["owner"], prop["predicate"], prop["property_shape"])
        if prop["owner"] != nodes[-1] or key not in verified_properties:
            raise ValueError("Candidate property is not verified in active domain")
        for end in range(1, len(nodes) + 1):
            prefix = tuple(nodes[:end])
            edge_signatures = tuple(
                (e["from"], e["predicate"], e["to"], e["property_shape"])
                for e in edges[:end - 1]
            )
            result_paths[(prefix, edge_signatures)] = (nodes[:end], edges[:end - 1])
        signature = (tuple(nodes), tuple(
            (e["from"], e["predicate"], e["to"], e["property_shape"]) for e in edges
        ), key)
        property_paths[signature] = (nodes, edges, prop)

    candidates, qualified_registry = [], {}
    for i, (_, (nodes, edges)) in enumerate(sorted(result_paths.items()), 1):
        cid = f"R{i}"
        candidates.append({
            "id": cid, "domain": domain, "kind": "result",
            "path": " → ".join(names[u] for u in nodes),
        })
        qualified_registry[cid] = {
            "domain": domain, "kind": "result", "node_uris": nodes[:],
            "edges": edges[:], "property": None, "target_shape_uri": nodes[-1],
        }
    for i, (_, (nodes, edges, prop)) in enumerate(sorted(property_paths.items()), 1):
        cid = f"P{i}"
        candidates.append({
            "id": cid, "domain": domain, "kind": "property",
            "path": " → ".join([*(names[u] for u in nodes), prop["name"]]),
            "property_name": prop["name"],
        })
        qualified_registry[cid] = {
            "domain": domain, "kind": "property", "node_uris": nodes[:],
            "edges": edges[:], "property": prop.copy(),
            "owner_shape_uri": prop["owner"],
            "property_predicate_uri": prop["predicate"],
        }
    return {
        "prompt": {
            "domain": domain, "question": prepared["prompt"]["question"],
            "candidates": candidates,
        },
        "registry": qualified_registry,
    }
