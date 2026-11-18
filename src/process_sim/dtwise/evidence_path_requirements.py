"""Resolve question requirements against one LLM-selected, evidenced path.

Conservative by design: ambiguity and unsupported requirements are errors,
not excuses to drop filters or guess which shape owns a predicate.
"""
from .unified_answer import extract_semantic_selection_requirements


def ground_path_requirements(question, catalog, mentioned, path):
    """Return (projections, filter_spec) for bind_evidenced_path.

    Only the existing SHACL-grounded extractor supplies requirements.
    Output ownership must be unique along the selected path. A single
    equality filter is currently supported by Unified IR's compact route.
    """
    if not isinstance(path, dict) or not isinstance(path.get("nodes"), list):
        raise ValueError("A selected evidence path is required")
    nodes = [tuple(n) for n in path["nodes"]]
    owners = {(e["domain"], e["shape"]): set(e["properties"])
              for e in catalog["entities"]}
    if not nodes or any(n not in owners for n in nodes):
        raise ValueError("Selected path contains unknown SHACL shapes")
    outputs, inputs = extract_semantic_selection_requirements(
        question, catalog, mentioned)
    if not outputs:
        raise ValueError("No explicit SHACL-grounded output requirement")
    projections = []
    for i, predicate in enumerate(outputs):
        matches = [j for j, node in enumerate(nodes)
                   if predicate in owners[node]]
        if len(matches) != 1:
            raise ValueError("Output predicate has no unique path owner: "
                             + predicate)
        projections.append({"node_index": matches[0], "predicate": predicate,
                            "as": f"value_{i}"})
    if len(inputs) > 1:
        raise ValueError("Multiple equality requirements are not yet supported")
    filter_spec = None
    if inputs:
        request = inputs[0]
        matches = [(j, p["predicate"])
                   for j, node in enumerate(nodes)
                   for p in request["candidate_properties"]
                   if p["domain"] == node[0]
                   and p["predicate"] in owners[node]]
        matches = sorted(set(matches))
        if len(matches) != 1:
            raise ValueError("Filter predicate has no unique path owner: "
                             + request["name"])
        filter_spec = {"node_index": matches[0][0],
                       "predicate": matches[0][1],
                       "op": "eq", "value": request["value"]}
    return projections, filter_spec
