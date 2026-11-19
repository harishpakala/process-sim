"""Standalone LLM-first semantic selection v2 boundary.

This module deliberately does not alter the production planner. Evidence is
supplied by the existing path enumerator, not discovered or invented here.
"""
import json

from .semantic_selection_v2 import validate_semantic_selection_v2


def _compact_evidence_paths(candidates):
    """Lossless selection IDs with concise display evidence.

    Original candidates remain authoritative for validation and IR binding.
    Avoid repeating JSON object keys and long mapping predicates in the
    model-facing catalog; no path, node, or property is filtered out.
    """
    compact = []
    for candidate in candidates:
        nodes = [[n["id"], n.get("domain", ""), n.get("shape", "")]
                 for n in candidate["nodes"]]
        properties = [[p["id"], p.get("label", "")]
                      for p in candidate["properties"]]
        steps = [[s["kind"], s.get("mapping_id", ""),
                  s.get("predicate", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]]
                 for s in candidate["steps"]]
        compact.append([candidate["id"], nodes, properties, steps])
    return compact


def select_semantic_v2(question, candidates, *, model, request_json,
                       ollama_host, timeout, keep_alive=None,
                       diagnostics=None):
    """Ask Ollama for a v2 selection; validate against its chosen path.

    candidates: [{id, nodes:[{id,...}], properties:[{id,...}], steps:[...]}].
    Only supplied IDs can appear in the output. Invalid output gets at most
    one LLM correction attempt; trusted code never rewrites its semantics.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question is required")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 32:
        raise ValueError("Provide 1 to 32 evidenced paths")
    paths = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Invalid evidence candidate")
        path_id = candidate.get("id")
        nodes = candidate.get("nodes")
        properties = candidate.get("properties")
        if (not isinstance(path_id, str) or not path_id.startswith("PATH_")
                or path_id in paths or not isinstance(nodes, list)
                or not nodes or not isinstance(properties, list)):
            raise ValueError("Invalid evidence candidate")
        node_ids = [n.get("id") for n in nodes if isinstance(n, dict)]
        prop_ids = [p.get("id") for p in properties if isinstance(p, dict)]
        if (len(node_ids) != len(nodes) or len(set(node_ids)) != len(node_ids)
                or len(prop_ids) != len(properties)
                or len(set(prop_ids)) != len(prop_ids)
                or not all(isinstance(x, str) and x for x in node_ids + prop_ids)):
            raise ValueError("Invalid evidence identifiers")
        paths[path_id] = (set(node_ids), set(prop_ids))

    system = (
        "You are a SHACL-evidence-bound semantic planner. Return ONLY a JSON "
        "object with exactly: path_id, operation, projections, group_by, "
        "count_target, aggregate_condition, filters, and optionally where, "
        "order_by, limit, distinct, optional_properties, count_property, anti_join. For unmatched entities across one verified mapping edge, set anti_join=true, operation=select, projections=[], filters=[], and omit other modifiers. For COUNT DISTINCT of a property, set distinct=true and count_property to its evidenced property ID. Use ONLY supplied "
        "PATH, node and property IDs. Supported operations: select, count, "
        "group_count. For a grouped count, project and group by the grouping "
        "property, choose the counted entity ID, and represent a numeric "
        "threshold as aggregate_condition {operator,value}, not a property "
        "filter. Use filters only for explicitly requested literal property "
        "constraints; otherwise use []. Shape/entity names are not literal "
        "filters. Boolean existence, absence and AND/OR/NOT belong in where. "
        "Use null for absent count_target and aggregate_condition. Do not "
        "invent joins: choose a supplied evidence path. If no valid plan is "
        "possible, return an unsupported operation to be rejected."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(
            {"question": question,
             "evidence_format": "[path_id, nodes[[node_id,domain,shape]], properties[[property_id,label]], steps[[kind,mapping_id,predicate_label]]]",
             "evidence_paths": _compact_evidence_paths(candidates)},
            ensure_ascii=False)},
    ]
    attempts = []
    for attempt in (1, 2):
        payload = {
            "model": model, "stream": False, "format": "json",
            "messages": list(messages),
            "options": {"temperature": 0},
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        response = request_json(ollama_host.rstrip("/") + "/api/chat",
                                payload, timeout)
        raw = response["message"]["content"]
        try:
            proposal = json.loads(raw)
            if not isinstance(proposal, dict):
                raise ValueError("Selection must be a JSON object")
            path_id = proposal.get("path_id")
            if path_id not in paths:
                raise ValueError("Missing or invalid evidence path ID")
            entities, properties = paths[path_id]
            selected = validate_semantic_selection_v2(
                proposal, path_ids={path_id}, entity_ids=entities,
                property_ids=properties)
        except (ValueError, TypeError, KeyError) as exc:
            attempts.append({"attempt": attempt, "status": "rejected",
                             "error": str(exc), "selection": raw})
            if diagnostics is not None:
                diagnostics["semantic_v2_attempts"] = list(attempts)
            if attempt == 2:
                raise ValueError(
                    "Semantic v2 selection rejected after two attempts: " +
                    "; ".join(a["error"] for a in attempts)) from exc
            messages.extend([
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "The selection failed strict evidence validation: " +
                    str(exc) + ". Return a complete corrected JSON selection. "
                    "Use only the supplied path, entity, and property IDs. "
                    "Do not invent or silently omit requested semantics.")},
            ])
            continue
        attempts.append({"attempt": attempt, "status": "accepted",
                         "selection": raw})
        if diagnostics is not None:
            diagnostics["semantic_v2_attempts"] = list(attempts)
        return selected
    raise AssertionError("Unreachable retry state")
