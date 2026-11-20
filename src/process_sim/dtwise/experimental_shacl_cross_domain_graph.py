"""Owner-aware, N-domain qualification of approved identifier mapping edges.

Consumes independently SHACL-qualified candidate registries. No semantic
selection, inferred identifier equivalence, SPARQL compilation or execution.
"""
from __future__ import annotations

from collections import defaultdict

from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def qualify_mapping_graph(mappings: dict[str, dict],
                          qualified_domains: dict[str, dict]) -> dict:
    """Build Qwen-facing identifier paths and mapping edges across N domains.

    qualified_domains maps each domain to the output of qualify_candidates().
    Candidate IDs are scoped to a domain, so stable composite IDs are used.
    All owner/path alternatives remain visible; no mapping is chosen here.
    """
    identifiers = {}
    by_predicate = defaultdict(list)
    for domain, qualified in sorted(qualified_domains.items()):
        if not isinstance(qualified, dict) or not isinstance(qualified.get("registry"), dict):
            raise SelectionContractError("Missing qualified candidate registry")
        prompt = qualified.get("prompt", {})
        if prompt.get("domain") != domain:
            raise SelectionContractError("Qualified candidate domain mismatch")
        display = {item["id"]: item for item in prompt.get("candidates", [])}
        for local_id, entry in sorted(qualified["registry"].items()):
            if entry.get("kind") != "property":
                continue
            prop = entry.get("property")
            nodes = entry.get("node_uris")
            if (entry.get("domain") != domain or not isinstance(prop, dict)
                    or not isinstance(nodes, list) or not nodes
                    or prop.get("owner") != nodes[-1]
                    or entry.get("owner_shape_uri") != nodes[-1]
                    or entry.get("property_predicate_uri") != prop.get("predicate")
                    or local_id not in display or display[local_id].get("kind") != "property"):
                raise SelectionContractError("Malformed qualified property path")
            candidate_id = f"{domain}:{local_id}"
            identifiers[candidate_id] = {
                "id": candidate_id, "domain": domain,
                "path": display[local_id]["path"],
                "owner_shape_uri": nodes[-1],
                "predicate": prop["predicate"],
            }
            by_predicate[(domain, prop["predicate"])].append(candidate_id)

    edges = []
    for mapping_id, mapping in sorted(mappings.items()):
        if mapping.get("verified") is not True:
            continue
        left, right = mapping["left_domain"], mapping["right_domain"]
        left_ids = sorted(by_predicate.get((left, mapping["left_property"]), []))
        right_ids = sorted(by_predicate.get((right, mapping["right_property"]), []))
        if not left_ids or not right_ids:
            continue
        edges.append({
            "id": mapping_id,
            "left_domain": left, "right_domain": right,
            "left_property": mapping["left_property"],
            "right_property": mapping["right_property"],
            "left_identifier_candidate_ids": left_ids,
            "right_identifier_candidate_ids": right_ids,
        })
    used = {cid for edge in edges for side in ("left", "right")
            for cid in edge[f"{side}_identifier_candidate_ids"]}
    return {
        "identifier_path_candidates": [identifiers[cid] for cid in sorted(used)],
        "mapping_candidates": edges,
    }


def validate_mapping_graph_selection(mapping_ids: list[str],
                                     identifier_path_ids: list[str],
                                     offered: dict, mappings: dict[str, dict]) -> list[dict]:
    """Validate selected edges and their endpoint paths without choosing intent.

    Each selected edge must have at least one selected owner-specific endpoint
    on each side. Disconnected selections and unselected dangling paths fail.
    """
    if (not isinstance(mapping_ids, list) or not mapping_ids
            or not isinstance(identifier_path_ids, list)
            or not identifier_path_ids
            or any(not isinstance(x, str) for x in mapping_ids + identifier_path_ids)
            or len(set(mapping_ids)) != len(mapping_ids)
            or len(set(identifier_path_ids)) != len(identifier_path_ids)):
        raise SelectionContractError("Invalid mapping graph selection")
    offered_edges = {e["id"]: e for e in offered["mapping_candidates"]}
    offered_paths = {p["id"] for p in offered["identifier_path_candidates"]}
    if any(x not in offered_edges for x in mapping_ids):
        raise SelectionContractError("Mapping ID was not offered")
    if any(x not in offered_paths for x in identifier_path_ids):
        raise SelectionContractError("Identifier path ID was not offered")
    selected = set(identifier_path_ids)
    domains = set()
    adjacency = defaultdict(set)
    used_paths = set()
    approved = []
    for mid in mapping_ids:
        edge = offered_edges[mid]
        source = mappings.get(mid)
        if source is None or source.get("verified") is not True or any(
            edge[k] != source[k] for k in
            ("left_domain", "right_domain", "left_property", "right_property")
        ):
            raise SelectionContractError("Mapping differs from approved declaration")
        left = selected.intersection(edge["left_identifier_candidate_ids"])
        right = selected.intersection(edge["right_identifier_candidate_ids"])
        if not left or not right:
            raise SelectionContractError("Selected mapping lacks identifier endpoints")
        used_paths.update(left | right)
        a, b = edge["left_domain"], edge["right_domain"]
        domains.update((a, b))
        adjacency[a].add(b)
        adjacency[b].add(a)
        approved.append(source)
    if used_paths != selected:
        raise SelectionContractError("Selected identifier path has no mapping edge")
    seen = set()
    frontier = [next(iter(domains))]
    while frontier:
        node = frontier.pop()
        if node not in seen:
            seen.add(node)
            frontier.extend(adjacency[node] - seen)
    if seen != domains:
        raise SelectionContractError("Selected mapping graph is disconnected")
    return approved
