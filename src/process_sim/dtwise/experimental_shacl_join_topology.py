"""Schema-derived shared-ancestor checks for future within-domain joins.

This module validates topology only. It does not interpret questions or compile
SPARQL; existing Phase 4 planners remain unchanged until explicitly migrated.
"""
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def verified_shared_ancestor(qualified, result_ids, *, ancestor_uri=None):
    """Return shared ancestor metadata for two verified sibling property paths.

    Uses the qualified registry's shape URIs and directed SHACL edges rather
    than labels, fixed path depths, or domain-specific property names.
    """
    if (not isinstance(result_ids, (list, tuple)) or len(result_ids) != 2 or
            any(not isinstance(rid, str) for rid in result_ids) or
            result_ids[0] == result_ids[1]):
        raise SelectionContractError("Join requires two distinct property IDs")
    candidates = {c["id"]: c for c in qualified["prompt"]["candidates"]
                  if c["kind"] == "property"}
    if any(rid not in candidates for rid in result_ids):
        raise SelectionContractError("Join requires verified property candidates")
    first, second = (qualified["registry"][rid] for rid in result_ids)
    domain = qualified["prompt"]["domain"]
    if any(p["domain"] != domain or p["kind"] != "property" for p in (first, second)):
        raise SelectionContractError("Join candidates must share active domain")
    for path in (first, second):
        nodes, edges = path["node_uris"], path["edges"]
        if not nodes or len(edges) != len(nodes) - 1:
            raise SelectionContractError("Disconnected join path")
        if path["property"]["owner"] != nodes[-1]:
            raise SelectionContractError("Invalid join property owner")
        for i, edge in enumerate(edges):
            if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
                raise SelectionContractError("Disconnected join edge")
    left, right = first["node_uris"], second["node_uris"]
    common = 0
    while common < min(len(left), len(right)) and left[common] == right[common]:
        if common and first["edges"][common - 1] != second["edges"][common - 1]:
            break
        common += 1
    if common < 1 or common == len(left) or common == len(right):
        raise SelectionContractError("Join requires a shared ancestor with two branches")
    owner = left[common - 1]
    if ancestor_uri is not None and owner != ancestor_uri:
        raise SelectionContractError("Join ancestor does not match requested shape")
    return {"domain": domain, "ancestor_uri": owner,
            "shared_node_uris": left[:common],
            "shared_edges": first["edges"][:common - 1],
            "branch_ids": list(result_ids)}
