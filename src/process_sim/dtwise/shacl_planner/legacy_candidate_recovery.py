"""Recover legacy candidate metadata from a verified SHACL index, without an LLM.

Candidate IDs are local to the saved record. Match each saved display path to
exactly one index topology; ambiguous labels or edges are never guessed.
"""
from __future__ import annotations

from collections import defaultdict

from process_sim.dtwise.experimental_shacl_subgraph import _short


class RecoveryError(ValueError):
    pass


def _name(index, uri):
    shape = index.shapes[uri]
    return next((v for v in shape.get("labels", [])
                 if "shacl shape" not in v.casefold()), _short(uri))


def recover_registry(record, index):
    """Return a registry for the selected IDs, or fail closed.

    Traversal is constrained by the number of segments in the saved path.
    It does not regenerate candidate IDs or invoke embedding/Qwen services.
    """
    offered = record.get("candidate_paths") or []
    lookup = {c.get("id"): c for c in offered}
    if len(lookup) != len(offered):
        raise RecoveryError("Duplicate candidate IDs")
    answer = record.get("answer") or {}
    ids = list(answer.get("projection_ids") or [])
    ids += list(answer.get("existence_ids") or [])
    ids += [f.get("property_id") for f in answer.get("filters") or []]
    ids += [o.get("property_id") for o in answer.get("order_by") or []]
    if answer.get("count_target_id"):
        ids.append(answer["count_target_id"])
    if not ids:
        raise RecoveryError("No selected candidate IDs")

    edges_by_owner = defaultdict(list)
    for edge in index.edges:
        edges_by_owner[edge["from"]].append(edge)
    properties_by_owner = index.properties
    registry = {}
    for cid in dict.fromkeys(ids):
        candidate = lookup.get(cid)
        if not candidate or candidate.get("kind") not in ("result", "property"):
            raise RecoveryError("Missing offered candidate " + str(cid))
        path = candidate.get("path")
        if not isinstance(path, str) or not path.strip():
            raise RecoveryError("Missing candidate path " + str(cid))
        parts = [part.strip() for part in path.split("→")]
        if not all(parts):
            raise RecoveryError("Malformed candidate path " + str(cid))
        is_property = candidate["kind"] == "property"
        shape_parts = parts[:-1] if is_property else parts
        if not shape_parts:
            raise RecoveryError("Missing shape context for " + str(cid))
        matches = []
        for root in index.shapes:
            if _name(index, root) != shape_parts[0]:
                continue
            frontier = [([root], [])]
            for expected in shape_parts[1:]:
                next_frontier = []
                for nodes, edges in frontier:
                    for edge in edges_by_owner.get(nodes[-1], []):
                        if edge["to"] not in nodes and _name(index, edge["to"]) == expected:
                            next_frontier.append((nodes + [edge["to"]], edges + [edge]))
                frontier = next_frontier
                if not frontier:
                    break
            for nodes, edges in frontier:
                if is_property:
                    for prop in properties_by_owner.get(nodes[-1], []):
                        if prop["name"] == parts[-1]:
                            matches.append({
                                "domain": index.domain, "kind": "property",
                                "node_uris": nodes, "edges": edges,
                                "property": prop.copy(),
                                "owner_shape_uri": nodes[-1],
                                "property_predicate_uri": prop["predicate"],
                            })
                else:
                    matches.append({
                        "domain": index.domain, "kind": "result",
                        "node_uris": nodes, "edges": edges,
                        "property": None, "target_shape_uri": nodes[-1],
                    })
        # Deduplicate equivalent graph paths, not different RDF predicates.
        unique = {}
        for match in matches:
            signature = (tuple(match["node_uris"]),
                         tuple((e["from"], e["predicate"], e["to"], e["property_shape"])
                               for e in match["edges"]),
                         (match["property"]["owner"], match["property"]["predicate"],
                          match["property"]["property_shape"])
                         if is_property else None)
            unique[signature] = match
        if len(unique) != 1:
            raise RecoveryError(
                f"Candidate {cid} path has {len(unique)} verified topology matches")
        registry[cid] = next(iter(unique.values()))
    return registry
