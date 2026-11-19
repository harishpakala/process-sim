"""One-call evidence-path and semantic-requirement selection.

Only IDs of SHACL-owned properties and pre-enumerated verified paths are
exposed to the model. Every choice is checked and rebound by trusted code.
"""
import json
import re
import time
from pathlib import Path

from .evidence_path_binding import bind_evidenced_path
from .unified_answer import resolve_shapes


def _label(iri):
    local = re.split(r"[/#:]", iri)[-1]
    return local[3:] if local.lower().startswith("has") and len(local) > 3 else local


def _write_prompt_diagnostics(diagnostics):
    path = diagnostics.get("path")
    if path:
        Path(path).write_text(
            json.dumps({k: v for k, v in diagnostics.items() if k != "path"}, indent=2),
            encoding="utf-8")



def _explicit_lookup_property_labels(question):
    """Only prune a fully specified cross-domain lookup; fail open otherwise.

    The full catalog remains authoritative for evidence-path revalidation.
    """
    match = re.fullmatch(
        r"\s*get\s+[A-Za-z][A-Za-z0-9_]*\s+"
        r"[A-Za-z][A-Za-z0-9_]*\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+for\s+[A-Za-z][A-Za-z0-9_]*\s+"
        r"[A-Za-z][A-Za-z0-9_]*\s+with\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+\S+\s*\.?\s*",
        question, re.I)
    return {part.casefold() for part in match.groups()} if match else None


def _path_join_predicates(path):
    """Preserve every SHACL or mapping predicate needed to describe a path."""
    required = set()
    for step in path["steps"]:
        for key in ("predicate", "left_predicate", "right_predicate"):
            predicate = step.get(key)
            if isinstance(predicate, str):
                required.add(predicate)
    return required


def select_evidence_plan(question, paths, catalog, index, mappings, *,
                         model, request_json, ollama_host, timeout,
                         keep_alive=None, prompt_diagnostics=None):
    """Select path, ordered projections, and optional equality in one call.

    A zero-edge candidate is a single SHACL shape; nonzero paths must be
    reverified by bind_evidenced_path. Unsupported operations fail closed.
    """
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ValueError("Provide 1 to 32 evidenced candidates")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    choices = []
    property_maps = []
    requested_labels = _explicit_lookup_property_labels(question)
    for i, path in enumerate(paths):
        nodes, steps = path["nodes"], path["steps"]
        if not nodes or len(nodes) != len(steps) + 1:
            raise ValueError("Invalid evidence candidate")
        if not steps and len(nodes) != 1:
            raise ValueError("Zero-edge path must have exactly one node")
        properties = {}
        labels = []
        join_predicates = _path_join_predicates(path)
        for j, node in enumerate(nodes):
            entity = owners.get(tuple(node))
            if entity is None:
                raise ValueError("Candidate contains unknown SHACL shape")
            labels.append({"index": j, "domain": entity["domain"],
                           "shape": entity["display_name"]})
            for predicate in entity["properties"]:
                if (requested_labels is not None
                        and _label(predicate).casefold() not in requested_labels
                        and predicate not in join_predicates):
                    continue
                key = "N" + str(j) + "P" + str(len(
                    [k for k in properties if k.startswith("N" + str(j) + "P")]))
                properties[key] = (j, predicate)
        property_maps.append(properties)
        choices.append({
            "id": "PATH_" + str(i), "nodes": labels,
            "steps": steps,
            "properties": [{"id": key, "label": _label(predicate),
                            "node": j}
                           for key, (j, predicate) in properties.items()],
        })
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Select one supplied evidence PATH ID and the SHACL property IDs "
             "needed to answer the question. Return ONLY JSON with exactly "
             "these keys: path_id, operation, projections, filter. "
             "path_id is a listed PATH ID or null. operation is 'select', "
             "'count', 'group_count', or 'unsupported'. projections is an ordered array of listed "
             "property IDs from the chosen path. filter is null or a JSON object "
             "with property (listed property ID), op ('eq' or 'contains'), "
             "value (literal), and optional ignore_case (boolean, only for contains). "
             "Use contains for substring matching, and ignore_case=true when "
             "the question requests case-insensitive matching. "
             "Never invent IDs, never omit requested outputs or conditions. "
             "For counting all entities, use operation='count' and empty projections. "
             "For counts grouped by a property, use operation='group_count' "
             "and project exactly the grouping property. For sorting and "
             "limits use operation='select' and project the sorted property. "
             "Branching joins or other unsupported operations return "
             "operation='unsupported'. Return no SPARQL."},
            {"role": "user", "content": json.dumps(
                {"question": question, "choices": choices},
                separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_text = "".join(message["content"] for message in payload["messages"])
        prompt_diagnostics.update({
            "stage": "experimental_evidence_selection",
            "candidate_path_count": len(paths),
            "candidate_property_count": sum(len(c["properties"]) for c in choices),
            "prompt_characters": len(prompt_text),
            "estimated_prompt_tokens": (len(prompt_text) + 3) // 4,
            "payload_bytes": len(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            "model": model,
            "timeout_seconds": timeout,
            "request_status": "started",
        })
        _write_prompt_diagnostics(prompt_diagnostics)
    started = time.perf_counter()
    try:
        response = request_json(ollama_host.rstrip("/") + "/api/chat",
                                payload, timeout)
    except Exception as exc:
        if prompt_diagnostics is not None:
            prompt_diagnostics.update({
                "request_status": "failed",
                "request_wall_seconds": round(time.perf_counter() - started, 3),
                "request_error_type": type(exc).__name__,
            })
            _write_prompt_diagnostics(prompt_diagnostics)
        raise
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "request_status": "completed",
            "request_wall_seconds": round(time.perf_counter() - started, 3),
            "ollama_prompt_tokens": response.get("prompt_eval_count"),
            "ollama_generated_tokens": response.get("eval_count"),
            "ollama_prompt_eval_seconds": response.get("prompt_eval_duration", 0) / 1e9,
            "ollama_generation_seconds": response.get("eval_duration", 0) / 1e9,
        })
        _write_prompt_diagnostics(prompt_diagnostics)
    try:
        result = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid evidence-selection JSON") from exc
    # Normalize harmless Ollama formatting variants before strict ID checks.
    # Do not invent paths, projections, or literal filters.
    if isinstance(result, dict):
        result = dict(result)
        if "properties" in result and "projections" not in result:
            result["projections"] = result.pop("properties")
        if "filter" not in result:
            result["filter"] = None
        if isinstance(result.get("operation"), str):
            operation = result["operation"].strip().lower()
            result["operation"] = "select" if operation == "get" else operation
    if not isinstance(result, dict) or set(result) != {
            "path_id", "operation", "projections", "filter"}:
        raise ValueError("Invalid evidence-selection structure")
    requested_count = bool(re.search(r"\bcount\b|\bhow many\b|\bnumber of\b|\bmore than\b", question, re.I))
    grouped = requested_count and bool(re.search(r"\b(?:for each|per|each|more than)\b", question, re.I))
    expected_operation = "group_count" if grouped else ("count" if requested_count else "select")
    if result["operation"] == "unsupported":
        raise ValueError("Unsupported evidence-selection operation")
    if result["operation"] != expected_operation:
        # A model may describe an aggregate's grouping-key projection as SELECT.
        # Recover only when the question explicitly requests grouped counts,
        # and the selected key is uniquely named in the question and SHACL.
        if not (expected_operation == "group_count"
                and result["operation"] == "select"
                and isinstance(result["projections"], list)
                and len(result["projections"]) == 1):
            raise ValueError("LLM selected an operation inconsistent with the question")
        selected = result["projections"][0]
        chosen = result["path_id"]
        if (not isinstance(chosen, str) or not re.fullmatch(r"PATH_\d+", chosen)
                or int(chosen[5:]) >= len(paths)
                or selected not in property_maps[int(chosen[5:])]):
            raise ValueError("Invalid grouping evidence selection")
        _, predicate = property_maps[int(chosen[5:])][selected]
        if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(_label(predicate))
                         + r"(?![A-Za-z0-9_])", question, re.I):
            raise ValueError("Grouped count key is not requested by the question")
    path_id = result["path_id"]
    if not isinstance(path_id, str) or not re.fullmatch(r"PATH_\d+", path_id):
        raise ValueError("Missing or invalid evidence path ID")
    i = int(path_id[5:])
    if i >= len(paths):
        raise ValueError("Invented evidence path ID")
    lookup = property_maps[i]
    projections = result["projections"]
    if (not isinstance(projections, list) or (not projections and expected_operation != 'count')
            or any(not isinstance(p, str) or p not in lookup for p in projections)
            or len(set(projections)) != len(projections)):
        raise ValueError("Missing, repeated, or invented projection ID")
    if expected_operation == 'count' and projections:
        raise ValueError("Ungrouped count cannot have property projections")
    if expected_operation == 'group_count' and len(projections) != 1:
        raise ValueError("Grouped count needs one grouping property")
    specs = [{"node_index": lookup[p][0], "predicate": lookup[p][1],
              "as": "value_" + str(j)} for j, p in enumerate(projections)]
    bound_filter = None
    # Do not validate unsolicited model filters: the question is authoritative.
    # A join property named in prose is not an equality-to-a-literal filter.
    # Extract only unambiguous explicit scalar constraints from the question.
    explicit = re.findall(
        r"\bwhere\s+([A-Za-z][A-Za-z0-9_]*)\s+is\s+(\S+)",
        question, flags=re.I)
    if not explicit:
        # "associated with DEXPI InstrumentationFunctions" is an entity
        # relationship, not an equality filter. Only SHACL-owned property
        # names can introduce the compact "with Property Value" syntax.
        possible = re.findall(
            r"\bwith\s+(?!more\s+than\b)([A-Za-z][A-Za-z0-9_]*)\s+"
            r"([^\s,;]+)", question, flags=re.I)
        owned_labels = {_label(predicate).casefold()
                        for _, predicate in lookup.values()}
        explicit = [(name, value) for name, value in possible
                    if name.casefold() in owned_labels]
    if len(explicit) > 1:
        raise ValueError("Multiple equality constraints are not supported")
    f = result["filter"]
    if f is not None:
        if (not isinstance(f, dict)
                or not {'property', 'op', 'value'}.issubset(f)
                or set(f) - {'property', 'op', 'value', 'ignore_case'}
                or not isinstance(f['property'], str)
                or f['property'] not in lookup
                or f['op'] not in ('eq', 'contains')
                or type(f['value']) not in (str, int, float, bool)
                or ('ignore_case' in f and (
                    f['op'] != 'contains' or type(f['ignore_case']) is not bool))):
            raise ValueError("Invalid evidence-selection filter")
        j, predicate = lookup[f['property']]
        bound_filter = {"node_index": j, "predicate": predicate,
                        "op": f['op'], "value": f['value']}
        if f.get('ignore_case') is True:
            bound_filter['ignore_case'] = True
    if explicit:
        property_name, literal = explicit[0]
        literal = literal.rstrip(".,;")
        candidates = [(j, predicate) for j, predicate in lookup.values()
                      if _label(predicate).casefold() == property_name.casefold()]
        if bound_filter is None:
            if len(set(candidates)) != 1:
                raise ValueError("LLM omitted an ambiguous explicit equality filter")
            j, predicate = candidates[0]
            bound_filter = {"node_index": j, "predicate": predicate,
                            "op": "eq", "value": literal}
        else:
            if (bound_filter["node_index"], bound_filter["predicate"]) not in candidates:
                raise ValueError("LLM selected a different equality-filter property")
            if bound_filter["op"] != "eq":
                raise ValueError("LLM selected an incorrect equality-filter operator")
            bound_filter["value"] = literal
    elif bound_filter is not None:
        # Never accept a scalar filter without a corresponding user request.
        # Semantic coverage validates the selected predicate and literal.
        if bound_filter["op"] == "eq":
            raise ValueError("Unrequested equality filter")
        if bound_filter["op"] == "contains":
            name = _label(bound_filter["predicate"])
            if not re.search(r"\b(?:containing|contains)\b", question, re.I):
                raise ValueError("Unrequested substring filter")
            if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(name)
                             + r"(?![A-Za-z0-9_])", question, re.I):
                raise ValueError("Substring filter property not requested")
            if bound_filter.get("ignore_case") and not re.search(
                    r"\b(?:ignoring\s+case|case[- ]insensitive)\b", question, re.I):
                raise ValueError("Unrequested case-insensitive filter")
    if re.search(r"\b(?:ignoring\s+case|case[- ]insensitive)\b", question, re.I):
        if bound_filter is None or bound_filter["op"] != "contains" or not bound_filter.get("ignore_case"):
            raise ValueError("Case-insensitive substring requirement omitted")
    threshold = None
    if expected_operation == 'group_count':
        number = re.search(r"\bmore than\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", question, re.I)
        if number:
            words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                     "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            threshold = words.get(number.group(1).lower())
            if threshold is None:
                threshold = int(number.group(1))
    order = None
    result_limit = None
    if expected_operation == 'select':
        if re.search(r"\b(?:ascending|descending|alphabetical(?:ly)?|sorted|order(?:ed)?)\b", question, re.I):
            if len(specs) != 1:
                raise ValueError("Ordering requires one unambiguous projected property")
            order = [{"as": specs[0]["as"], "direction":
                      "desc" if re.search(r"\bdescending\b", question, re.I) else "asc"}]
        m = re.search(r"\b(?:first|top|limit)\s+(\d+|ten)\b", question, re.I)
        if m:
            result_limit = 10 if m.group(1).lower() == "ten" else int(m.group(1))
            if not 1 <= result_limit <= 10000:
                raise ValueError("Requested limit out of bounds")
    # Reuse the grounded equality requirements; do not independently
    # reinterpret an entity mention following "with" as a scalar filter.
    if explicit and bound_filter is None:
        raise ValueError("LLM omitted an explicit equality filter")
    if not paths[i]["steps"]:
        node = tuple(paths[i]["nodes"][0])
        plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "n0", "domain": node[0], "shape": node[1]}],
            "edges": [],
            "projections": [{"entity": "n0", "predicate": p["predicate"],
                             "as": p["as"]} for p in specs],
            "filters": ({"op": bound_filter["op"], "entity": "n0",
                         "predicate": bound_filter["predicate"],
                         "value": bound_filter["value"],
                         **({"ignore_case": True} if bound_filter.get("ignore_case") else {})}
                        if bound_filter else None),
            "operation": {"type": expected_operation, **({"having_min": threshold} if threshold is not None else {})},
            "return_entities": False,
        }
        if order is not None:
            plan["order_by"] = order
        if result_limit is not None:
            plan["result_limit"] = result_limit
    else:
        if bound_filter is not None and bound_filter["op"] != "eq":
            raise ValueError("Non-equality filters on multi-hop paths are not yet supported")
        plan = bind_evidenced_path(paths[i], catalog, mappings,
                                  projections=specs, filter_spec=bound_filter)
        plan["operation"] = {"type": expected_operation, **({"having_min": threshold} if threshold is not None else {})}
        if order is not None:
            plan["order_by"] = order
        if result_limit is not None:
            plan["result_limit"] = result_limit
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded", "choice": path_id}
