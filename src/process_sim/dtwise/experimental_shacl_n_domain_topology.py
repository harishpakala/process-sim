"""Independent owner/path continuity validation for selected N-domain plans.

No inferred RDF types, semantic intent decisions, SPARQL, or instance claims.
"""
from __future__ import annotations

from collections import defaultdict

from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def _path(entry: dict) -> tuple:
    nodes = entry.get("node_uris")
    edges = entry.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise SelectionContractError("Malformed selected SHACL path")
    if len(edges) != len(nodes) - 1:
        raise SelectionContractError("Malformed selected SHACL edge sequence")
    for i, edge in enumerate(edges):
        if edge.get("from") != nodes[i] or edge.get("to") != nodes[i + 1]:
            raise SelectionContractError("Selected SHACL edges do not match path")
    return tuple(nodes)


def _connected(a: tuple, b: tuple) -> bool:
    """Same verified root-to-node chain (including ancestor/descendant)."""
    return a[:len(b)] == b or b[:len(a)] == a


def validate_selected_topology(selection: dict, prepared: dict) -> None:
    """Reject result/identifier disconnects and unsupported mapping transitions.

    Registry paths are assumed independently SHACL-qualified at preparation.
    A domain's selected identifier paths must be on a common verified chain;
    this deliberately abstains on cross-owner relationships without evidence.
    """
    if selection.get("status") != "selected":
        return
    prompt = prepared["prompt"]
    registry = prepared["result_registry"]
    result_candidates = {c["id"]: c for c in prompt["result_candidates"]}
    identifier_candidates = {c["id"]: c for c in prompt["identifier_path_candidates"]}
    mappings = {c["id"]: c for c in prompt["mapping_candidates"]}
    results = defaultdict(list)
    identifiers = defaultdict(list)
    for cid in selection["result_ids"]:
        if cid not in registry or cid not in result_candidates:
            raise SelectionContractError("Unknown selected result path")
        entry = registry[cid]
        nodes = _path(entry)
        if entry.get("domain") != result_candidates[cid]["domain"]:
            raise SelectionContractError("Result domain mismatch")
        if entry.get("kind") == "result":
            if entry.get("target_shape_uri") != nodes[-1]:
                raise SelectionContractError("Result owner mismatch")
        elif entry.get("kind") == "property":
            prop = entry.get("property")
            if (not isinstance(prop, dict) or prop.get("owner") != nodes[-1]
                    or entry.get("owner_shape_uri") != nodes[-1]
                    or entry.get("property_predicate_uri") != prop.get("predicate")):
                raise SelectionContractError("Result property owner mismatch")
        else:
            raise SelectionContractError("Unknown selected result kind")
        results[entry["domain"]].append(nodes)
    for cid in selection["identifier_path_ids"]:
        if cid not in registry or cid not in identifier_candidates:
            raise SelectionContractError("Unknown selected identifier path")
        entry = registry[cid]
        candidate = identifier_candidates[cid]
        nodes = _path(entry)
        prop = entry.get("property")
        if (entry.get("kind") != "property" or entry.get("domain") != candidate["domain"]
                or not isinstance(prop, dict) or prop.get("owner") != nodes[-1]
                or entry.get("owner_shape_uri") != nodes[-1]
                or entry.get("property_predicate_uri") != candidate["predicate"]
                or prop.get("predicate") != candidate["predicate"]
                or candidate["owner_shape_uri"] != nodes[-1]):
            raise SelectionContractError("Identifier owner/predicate mismatch")
        identifiers[entry["domain"]].append((cid, nodes, candidate["predicate"]))
    for domain, paths in results.items():
        if not identifiers[domain]:
            raise SelectionContractError("Result domain lacks selected identifier")
        for path in paths:
            if not any(_connected(path, identifier_path)
                       for _, identifier_path, _ in identifiers[domain]):
                raise SelectionContractError("Result path disconnected from identifier owner")
    for domain, paths in identifiers.items():
        # All endpoints in an intermediate domain must refer to the same
        # verified owner chain and identifier predicate. Otherwise a mapping
        # chain could silently switch subjects or identifier semantics.
        for i, (_, a, pred_a) in enumerate(paths):
            for _, b, pred_b in paths[i + 1:]:
                if pred_a != pred_b:
                    raise SelectionContractError("Unverified identifier type transition")
                if not _connected(a, b):
                    raise SelectionContractError("Disconnected identifier owners")
    for mid in selection["mapping_ids"]:
        if mid not in mappings:
            raise SelectionContractError("Unknown selected mapping")
        mapping = mappings[mid]
        for side in ("left", "right"):
            domain = mapping[f"{side}_domain"]
            predicate = mapping[f"{side}_property"]
            allowed = set(mapping[f"{side}_identifier_candidate_ids"])
            if not any(cid in allowed and pred == predicate
                       for cid, _, pred in identifiers[domain]):
                raise SelectionContractError("Selected mapping endpoint lacks verified path")
