"""Evidence-verified binding of a selected path to Unified IR 1.0.

Experimental and intentionally not wired into the live planner.
"""
from .unified_answer import enumerate_evidenced_paths


def bind_evidenced_path(path, catalog, mappings, *, projections, filter_spec=None):
    """Bind explicit (node_index, predicate) projections to a verified path.

    Re-enumeration prevents a caller or model from smuggling invented edges.
    This function does not infer intent, choose a path, or compile SPARQL.
    """
    if not isinstance(path, dict) or not isinstance(path.get("nodes"), list):
        raise ValueError("Invalid selected path")
    nodes, steps = path["nodes"], path.get("steps")
    if not isinstance(steps, list) or not steps or len(nodes) != len(steps) + 1:
        raise ValueError("Invalid selected path")
    if len(steps) > 8:
        raise ValueError("Path exceeds supported hop bound")
    if not isinstance(projections, list):
        raise ValueError("Projections must be a list")
    try:
        start, end = tuple(nodes[0]), tuple(nodes[-1])
        normalized_nodes = [tuple(node) for node in nodes]
    except (TypeError, ValueError):
        raise ValueError("Invalid path nodes") from None
    if any(len(node) != 2 or not all(isinstance(v, str) for v in node)
           for node in normalized_nodes):
        raise ValueError("Invalid path nodes")
    # Exact evidence check, not just structural checks on model output.
    valid = enumerate_evidenced_paths(
        catalog, mappings, start, end, max_hops=len(steps), max_paths=256)
    if not any(p["nodes"] == normalized_nodes and p["steps"] == steps
               for p in valid):
        raise ValueError("Selected path is not supported by verified evidence")
    owners = {(e["domain"], e["shape"]): set(e["properties"])
              for e in catalog["entities"]}
    aliases = [f"n{i}" for i in range(len(nodes))]

    def property_at(spec):
        if not isinstance(spec, dict) or type(spec.get("node_index")) is not int:
            raise ValueError("Property must specify an integer node_index")
        i, predicate = spec["node_index"], spec.get("predicate")
        if not 0 <= i < len(nodes) or predicate not in owners[normalized_nodes[i]]:
            raise ValueError("Predicate not owned by selected SHACL shape")
        return aliases[i], predicate

    bound_projections = []
    used_names = set()
    for spec in projections:
        alias, predicate = property_at(spec)
        name = spec.get("as")
        if not isinstance(name, str) or not name.isidentifier() or name in used_names:
            raise ValueError("Projection alias must be a unique identifier")
        used_names.add(name)
        bound_projections.append({"entity": alias, "predicate": predicate,
                                  "as": name})
    bound_filter = None
    if filter_spec is not None:
        alias, predicate = property_at(filter_spec)
        if filter_spec.get("op") != "eq" or not isinstance(
                filter_spec.get("value"), (str, int, float, bool)):
            raise ValueError("Only explicit scalar equality filters are supported")
        bound_filter = {"op": "eq", "entity": alias, "predicate": predicate,
                        "value": filter_spec["value"]}
    edges = []
    for i, step in enumerate(steps):
        edge = {"kind": step["kind"], "from": aliases[i],
                "to": aliases[i + 1]}
        if step["kind"] == "shacl":
            edge["predicate"] = step["predicate"]
        else:
            edge.update({"mapping_id": step["mapping_id"],
                         "left_predicate": step["left_predicate"],
                         "right_predicate": step["right_predicate"]})
        edges.append(edge)
    return {
        "ir_version": "1.0",
        "entities": [{"alias": aliases[i], "domain": node[0],
                      "shape": node[1]} for i, node in enumerate(normalized_nodes)],
        "edges": edges,
        "projections": bound_projections,
        "filters": bound_filter,
        "operation": {"type": "select"},
        "return_entities": False,
    }
