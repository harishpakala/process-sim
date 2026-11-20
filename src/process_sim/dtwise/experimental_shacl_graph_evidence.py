"""Bounded SHACL subgraph evidence for local LLM query planning.

Only verified qualified paths are included. This is model context, not
authorization: the original qualified registry remains the source of truth.
"""


def graph_evidence(qualified):
    """Merge qualified property paths into a deduplicated directed subgraph."""
    registry = qualified["registry"]
    candidates = [c for c in qualified["prompt"]["candidates"]
                  if c["kind"] == "property"]
    nodes, edges, properties = {}, {}, {}
    for candidate in candidates:
        cid = candidate["id"]
        path = registry[cid]
        for uri in path["node_uris"]:
            nodes[uri] = {"uri": uri}
        for edge in path["edges"]:
            key = (edge["from"], edge["predicate"], edge["to"],
                   edge["property_shape"])
            edges[key] = {
                "from": edge["from"], "predicate": edge["predicate"],
                "to": edge["to"], "property_shape": edge["property_shape"],
            }
        prop = path["property"]
        key = (prop["owner"], prop["predicate"], prop["property_shape"])
        item = properties.setdefault(key, {
            "owner": prop["owner"], "predicate": prop["predicate"],
            "property_shape": prop["property_shape"], "name": prop["name"],
            "candidate_ids": [],
        })
        item["candidate_ids"].append(cid)
    return {
        "domain": qualified["prompt"]["domain"],
        "nodes": [nodes[k] for k in sorted(nodes)],
        "edges": [edges[k] for k in sorted(edges)],
        "properties": [properties[k] for k in sorted(properties)],
        "candidate_paths": candidates,
    }
