"""LLM selection of connected, SHACL-grounded mapping subgraphs.

This module never synthesizes mapping edges: every selectable edge is backed
by a verified mapping and predicates owned by its endpoint shapes.
"""
import json
import re
import time

from .unified_answer import resolve_shapes
from .experimental_evidence_selection import _write_prompt_diagnostics


def _label(iri):
    local = re.split(r"[/#:]", iri)[-1]
    return local[3:] if local.lower().startswith("has") and len(local) > 3 else local


def select_evidence_subgraph(question, anchors, catalog, index, mappings, *,
                             model, request_json, ollama_host, timeout,
                             keep_alive=None, prompt_diagnostics=None):
    # This first subgraph implementation handles entity-return joins only.
    # Never silently discard requested projections, aggregates or filters.
    if re.search(r"\\b(?:return|list|show|display)\\s+"
                 r"[A-Za-z][A-Za-z0-9_]*\\s*$", question.rstrip(" ."), re.I):
        raise ValueError("Subgraph property projections are not yet supported")
    if re.search(r"\\b(?:where|count|how many)\\b", question, re.I):
        raise ValueError("Filtered or aggregate subgraphs are not yet supported")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    nodes = sorted(set(anchors))
    if len(nodes) < 3 or len(nodes) > 12:
        raise ValueError("Connected subgraph selection requires 3 to 12 named shapes")
    if any(n not in owners for n in nodes):
        raise ValueError("Unknown named SHACL shape")
    candidates = []
    for mapping in mappings or []:
        if mapping.get("verified") is not True or not mapping.get("evidence_ids"):
            continue
        left_domain, right_domain = mapping.get("left_domain"), mapping.get("right_domain")
        left_predicate, right_predicate = mapping.get("left_property"), mapping.get("right_property")
        left_nodes = [n for n in nodes if n[0] == left_domain
                      and left_predicate in owners[n]["properties"]]
        right_nodes = [n for n in nodes if n[0] == right_domain
                       and right_predicate in owners[n]["properties"]]
        for left in left_nodes:
            for right in right_nodes:
                if left == right:
                    continue
                candidates.append({
                    "id": "E" + str(len(candidates)),
                    "from": nodes.index(left), "to": nodes.index(right),
                    "mapping_id": mapping["id"],
                    "left_predicate": left_predicate,
                    "right_predicate": right_predicate,
                    "key": _label(left_predicate),
                })
    if not candidates:
        raise ValueError("No verified mapping edges between named shapes")
    if len(candidates) > 80:
        raise ValueError("Too many verified mapping edges; narrow the question")
    # Enumerate only evidence-backed spanning trees. The model selects
    # semantic alternatives, not arbitrary edge sets requiring graph repair.
    using = re.search(r"\busing\s+(.+?)(?:[.;]|$)", question, re.I)
    requested = None
    if using:
        requested = {x.strip().casefold() for x in
                     re.split(r"\s+and\s+|,", using.group(1), flags=re.I)}
    eligible = []
    for edge in candidates:
        left = _label(edge["left_predicate"]).casefold()
        right = _label(edge["right_predicate"]).casefold()
        if requested is None or (left in requested and right in requested):
            eligible.append(edge)

    trees = set()
    limit = 64

    def enumerate_trees(selected, visited, keys):
        if len(trees) >= limit:
            return
        if len(visited) == len(nodes):
            if requested is None or requested.issubset(keys):
                trees.add(tuple(sorted((e["id"] for e in selected),
                                       key=lambda x: int(x[1:]))))
            return
        for edge in eligible:
            a, b = edge["from"], edge["to"]
            if (a in visited) == (b in visited):
                continue
            if edge["id"] in {e["id"] for e in selected}:
                continue
            other = b if a in visited else a
            enumerate_trees(
                selected + [edge], visited | {other},
                keys | {_label(edge["left_predicate"]).casefold(),
                        _label(edge["right_predicate"]).casefold()})
            if len(trees) >= limit:
                return

    # Deduplicate traversal orders before exposing alternatives to the LLM.
    enumerate_trees([], {0}, set())
    unique = sorted(trees)
    if not unique:
        raise ValueError(
            "No verified spanning tree covers all named shapes and requested join keys")
    if len(trees) >= limit:
        raise ValueError("More than 63 candidate spanning trees; narrow the question")
    by_id = {e["id"]: e for e in candidates}
    options = [
        {"id": "TREE_" + str(i), "edges": [
            {"id": edge_id, "from": by_id[edge_id]["from"],
             "to": by_id[edge_id]["to"],
             "key": _label(by_id[edge_id]["left_predicate"])}
            for edge_id in tree]}
        for i, tree in enumerate(unique)]
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Select the best VERIFIED CONNECTED TREE for the user's "
             "requested join semantics. All listed trees already satisfy "
             "structural and join-key checks. Return ONLY JSON with exactly "
             "one key: tree_id. Its value must be one listed TREE ID. "
             "Do not invent IDs or return SPARQL."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "nodes": [{"index": i, "domain": n[0],
                           "shape": owners[n].get("display_name", n[1])}
                          for i, n in enumerate(nodes)],
                "trees": options}, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_diagnostics["llm_candidate_payload"] = payload
        prompt_diagnostics.update({
            "stage": "experimental_evidence_subgraph",
            "candidate_edge_count": len(candidates),
            "candidate_node_count": len(nodes),
            "candidate_tree_count": len(options),
            "request_status": "started",
            "subgraph_attempts": [],
        })
        _write_prompt_diagnostics(prompt_diagnostics)
    for attempt in range(2):
        started = time.perf_counter()
        selection = None
        try:
            response = request_json(ollama_host.rstrip("/") + "/api/chat",
                                    payload, timeout)
            selection = json.loads(response["message"]["content"])
            if not isinstance(selection, dict) or set(selection) != {"tree_id"}:
                raise ValueError("Invalid tree-selection structure")
            tree_id = selection["tree_id"]
            if (not isinstance(tree_id, str)
                    or not re.fullmatch(r"TREE_\d+", tree_id)
                    or int(tree_id[5:]) >= len(options)):
                raise ValueError("Unknown verified tree ID")
            ids = list(unique[int(tree_id[5:])])
            selected = [by_id[edge_id] for edge_id in ids]
        except (KeyError, TypeError, ValueError) as exc:
            if prompt_diagnostics is not None:
                prompt_diagnostics["subgraph_attempts"].append({
                    "attempt": attempt + 1, "status": "rejected",
                    "reason": str(exc), "selection": selection,
                })
                _write_prompt_diagnostics(prompt_diagnostics)
            if attempt:
                raise
            payload["messages"].append({
                "role": "assistant",
                "content": json.dumps(selection) if selection is not None else "{}",
            })
            payload["messages"].append({
                "role": "user",
                "content": "Selection rejected: " + str(exc)
                + ". Return exactly {\"tree_id\":\"TREE_N\"} "
                "with one listed TREE ID.",
            })
            continue
        if prompt_diagnostics is not None:
            prompt_diagnostics["subgraph_attempts"].append({
                "attempt": attempt + 1, "status": "accepted",
                "selected_tree_id": tree_id, "selected_edge_ids": ids,
                "request_wall_seconds": round(time.perf_counter() - started, 3),
            })
            prompt_diagnostics["request_status"] = "completed"
            _write_prompt_diagnostics(prompt_diagnostics)
        break
    edges = [{
        "kind": "mapping", "from": "n" + str(e["from"]),
        "to": "n" + str(e["to"]), "mapping_id": e["mapping_id"],
        "left_predicate": e["left_predicate"],
        "right_predicate": e["right_predicate"],
    } for e in selected]
    plan = {
        "ir_version": "1.0",
        "entities": [{"alias": "n" + str(i), "domain": n[0], "shape": n[1]}
                     for i, n in enumerate(nodes)],
        "edges": edges, "projections": [], "filters": None,
        "operation": {"type": "select"}, "return_entities": True,
    }
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_CONNECTED_SUBGRAPH",
        "selected_edge_ids": ids,
    }
