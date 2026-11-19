"""LLM selection of connected, SHACL-grounded mapping subgraphs.

This module never synthesizes mapping edges: every selectable edge is backed
by a verified mapping and predicates owned by its endpoint shapes.
"""
import json
import re
import time

from .unified_answer import resolve_shapes


def _label(iri):
    local = re.split(r"[/#]", iri)[-1]
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
    choices = [{"id": e["id"], "from": e["from"], "to": e["to"],
                "key": e["key"]} for e in candidates]
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Select verified mapping EDGE IDs to connect every named entity "
             "into one connected graph. Return ONLY JSON with exactly one key: "
             "edge_ids (array of listed edge IDs). Select the smallest "
             "connected set satisfying all explicit join keys. Do not invent "
             "IDs or omit entities. No SPARQL."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "nodes": [{"index": i, "domain": n[0],
                           "shape": owners[n].get("display_name", n[1])}
                          for i, n in enumerate(nodes)],
                "edges": choices}, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "stage": "experimental_evidence_subgraph",
            "candidate_edge_count": len(candidates),
            "candidate_node_count": len(nodes),
            "request_status": "started",
        })
    start = time.perf_counter()
    try:
        response = request_json(ollama_host.rstrip("/") + "/api/chat",
                                payload, timeout)
        selection = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid evidence-subgraph LLM response") from exc
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "request_status": "completed",
            "request_wall_seconds": round(time.perf_counter() - start, 3),
            "ollama_prompt_tokens": response.get("prompt_eval_count"),
            "ollama_generated_tokens": response.get("eval_count"),
        })
    if not isinstance(selection, dict) or set(selection) != {"edge_ids"}:
        raise ValueError("Invalid evidence-subgraph selection structure")
    ids = selection["edge_ids"]
    by_id = {e["id"]: e for e in candidates}
    if (not isinstance(ids, list) or not ids or
            any(not isinstance(x, str) or x not in by_id for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Unknown or repeated evidence-subgraph edge ID")
    selected = [by_id[x] for x in ids]
    # A tree is sufficient to connect the requested shapes. Reject cycles,
    # disconnected graphs and superfluous edges rather than hiding mistakes.
    if len(selected) != len(nodes) - 1:
        raise ValueError("Selected evidence subgraph is not a spanning tree")
    parent = list(range(len(nodes)))

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for edge in selected:
        a, b = root(edge["from"]), root(edge["to"])
        if a == b:
            raise ValueError("Selected evidence subgraph contains a cycle")
        parent[a] = b
    if len({root(i) for i in range(len(nodes))}) != 1:
        raise ValueError("Selected evidence subgraph is disconnected")
    # Check explicit join-key requirements against the actual selected edges.
    using = re.search(r"\busing\s+(.+?)(?:[.;]|$)", question, re.I)
    if using:
        requested = {x.strip().casefold() for x in
                     re.split(r"\s+and\s+|,", using.group(1), flags=re.I)}
        actual = {_label(e["left_predicate"]).casefold() for e in selected}
        actual |= {_label(e["right_predicate"]).casefold() for e in selected}
        if not requested.issubset(actual):
            raise ValueError("Selected subgraph omits a requested join key")
        if any(_label(e["left_predicate"]).casefold() not in requested
               or _label(e["right_predicate"]).casefold() not in requested
               for e in selected):
            raise ValueError("Selected subgraph uses an unrequested join key")
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
