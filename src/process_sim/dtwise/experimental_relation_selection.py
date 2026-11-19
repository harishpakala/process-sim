"""Compact LLM-first operation selection over verified direct mappings.

No benchmark wording is matched: the LLM decides whether the requested
relationship is positive, negative, or outside this entity-return scope.
"""
import json
import time

from .unified_answer import resolve_shapes
from .experimental_evidence_selection import _label, _write_prompt_diagnostics


def select_evidence_relation(question, anchors, catalog, index, mappings, *,
                             model, request_json, ollama_host, timeout,
                             keep_alive=None, prompt_diagnostics=None):
    if len(anchors) != 2:
        return None
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    edges = []
    for mapping in mappings or []:
        if mapping.get("verified") is not True or not mapping.get("evidence_ids"):
            continue
        for source, target in ((0, 1), (1, 0)):
            left, right = anchors[source], anchors[target]
            if (mapping.get("left_domain") == left[0]
                    and mapping.get("right_domain") == right[0]
                    and mapping.get("left_property") in owners[left]["properties"]
                    and mapping.get("right_property") in owners[right]["properties"]):
                edges.append({
                    "id": "M" + str(len(edges)), "mapping": mapping,
                    "source": source, "target": target,
                    "left": mapping["left_property"],
                    "right": mapping["right_property"]})
    if not edges:
        return None
    # Avoid claiming that this compact direct-mapping selector supports
    # projection, filtering or aggregation; let the full selector handle them.
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Interpret the user's question using only verified mapping options. "
             "Return JSON with exactly: operation, mapping_id, return_node. "
             "operation must be 'join', 'anti_join', or 'unsupported'. "
             "Choose anti_join ONLY when the question asks for entities with "
             "NO matching related entity. return_node is 0 or 1, identifying "
             "the requested output entity type. For property outputs, "
             "filters, counts, or uncertain semantics choose unsupported. "
             "mapping_id must be one listed M ID, or null for unsupported. "
             "Do not invent identifiers or output SPARQL."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "nodes": [{"id": i, "domain": n[0],
                           "shape": owners[n]["display_name"]}
                          for i, n in enumerate(anchors)],
                "mappings": [{"id": e["id"], "from": e["source"],
                              "to": e["target"],
                              "left_key": _label(e["left"]),
                              "right_key": _label(e["right"])}
                             for e in edges]}, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "stage": "experimental_relation_selection",
            "candidate_mapping_count": len(edges),
            "request_status": "started"})
        _write_prompt_diagnostics(prompt_diagnostics)
    started = time.perf_counter()
    try:
        response = request_json(ollama_host.rstrip("/") + "/api/chat",
                                payload, timeout)
        choice = json.loads(response["message"]["content"])
    except (ValueError, KeyError, TypeError, TimeoutError) as exc:
        if prompt_diagnostics is not None:
            prompt_diagnostics.update({
                "request_status": "failed",
                "request_error_type": type(exc).__name__,
                "request_wall_seconds": round(time.perf_counter() - started, 3)})
            _write_prompt_diagnostics(prompt_diagnostics)
        raise
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "request_status": "completed",
            "request_wall_seconds": round(time.perf_counter() - started, 3),
            "selection": choice})
        _write_prompt_diagnostics(prompt_diagnostics)
    if not isinstance(choice, dict) or set(choice) != {
            "operation", "mapping_id", "return_node"}:
        raise ValueError("Invalid relation selection structure")
    operation = choice["operation"]
    if operation == "unsupported":
        if choice["mapping_id"] is not None:
            raise ValueError("Unsupported relation must not select mapping")
        return None
    if operation not in ("join", "anti_join"):
        raise ValueError("Unknown relation operation")
    if type(choice["return_node"]) is not int or choice["return_node"] not in (0, 1):
        raise ValueError("Invalid relation return node")
    selected = next((e for e in edges if e["id"] == choice["mapping_id"]), None)
    if selected is None:
        raise ValueError("Unknown verified relation mapping ID")
    # Bind the exact verified predicates and mapping. Orient the edge
    # from the returned entity for anti-join correlation.
    source = choice["return_node"]
    other = 1 - source
    mapping = selected["mapping"]
    if selected["source"] == source:
        left, right = selected["left"], selected["right"]
    else:
        left, right = selected["right"], selected["left"]
    plan = {
        "ir_version": "1.0",
        "entities": [
            {"alias": "n0", "domain": anchors[source][0],
             "shape": anchors[source][1]},
            {"alias": "n1", "domain": anchors[other][0],
             "shape": anchors[other][1]}],
        "edges": [{"kind": "mapping", "from": "n0", "to": "n1",
                   "mapping_id": mapping["id"],
                   "left_predicate": left, "right_predicate": right}],
        "projections": [], "filters": None,
        "operation": {"type": "select"}, "return_entities": True,
    }
    if operation == "anti_join":
        plan["anti_join"] = {"from": "n0", "to": "n1"}
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_LLM_RELATION",
        "operation": operation, "mapping_id": mapping["id"]}
