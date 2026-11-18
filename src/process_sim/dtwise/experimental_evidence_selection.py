"""One-call evidence-path and semantic-requirement selection.

Only IDs of SHACL-owned properties and pre-enumerated verified paths are
exposed to the model. Every choice is checked and rebound by trusted code.
"""
import json
import re

from .evidence_path_binding import bind_evidenced_path
from .unified_answer import resolve_shapes


def _label(iri):
    local = re.split(r"[/#:]", iri)[-1]
    return local[3:] if local.lower().startswith("has") and len(local) > 3 else local


def select_evidence_plan(question, paths, catalog, index, mappings, *,
                         model, request_json, ollama_host, timeout,
                         keep_alive=None):
    """Select path, ordered projections, and optional equality in one call.

    A zero-edge candidate is a single SHACL shape; nonzero paths must be
    reverified by bind_evidenced_path. Unsupported operations fail closed.
    """
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ValueError("Provide 1 to 32 evidenced candidates")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    choices = []
    property_maps = []
    for i, path in enumerate(paths):
        nodes, steps = path["nodes"], path["steps"]
        if not nodes or len(nodes) != len(steps) + 1:
            raise ValueError("Invalid evidence candidate")
        if not steps and len(nodes) != 1:
            raise ValueError("Zero-edge path must have exactly one node")
        properties = {}
        labels = []
        for j, node in enumerate(nodes):
            entity = owners.get(tuple(node))
            if entity is None:
                raise ValueError("Candidate contains unknown SHACL shape")
            labels.append({"index": j, "domain": entity["domain"],
                           "shape": entity["display_name"]})
            for predicate in entity["properties"]:
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
             "path_id is a listed PATH ID or null. operation is 'select' "
             "or 'unsupported'. projections is an ordered array of listed "
             "property IDs from the chosen path. filter is null or "
             "{\"property\":\"N0P0\",\"op\":\"eq\",\"value\":\"literal\"}. "
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
    response = request_json(ollama_host.rstrip("/") + "/api/chat",
                            payload, timeout)
    try:
        result = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid evidence-selection JSON") from exc
    if not isinstance(result, dict) or set(result) != {
            "path_id", "operation", "projections", "filter"}:
        raise ValueError("Invalid evidence-selection structure")
    requested_count = bool(re.search(r"\bcount\b|\bhow many\b|\bnumber of\b|\bmore than\b", question, re.I))
    grouped = requested_count and bool(re.search(r"\b(?:for each|per|each|more than)\b", question, re.I))
    expected_operation = "group_count" if grouped else ("count" if requested_count else "select")
    if result["operation"] != expected_operation:
        raise ValueError("LLM selected an operation inconsistent with the question")
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
    f = result["filter"]
    if f is not None:
        if (not isinstance(f, dict) or set(f) != {"property", "op", "value"}
                or not isinstance(f["property"], str)
                or f["property"] not in lookup or f["op"] != "eq"
                or type(f["value"]) not in (str, int, float, bool)):
            raise ValueError("Invalid evidence-selection filter")
        j, predicate = lookup[f["property"]]
        bound_filter = {"node_index": j, "predicate": predicate,
                        "op": "eq", "value": f["value"]}
    # A join property named in prose is not an equality-to-a-literal filter.
    # Extract only unambiguous explicit scalar constraints from the question.
    explicit = re.findall(
        r"\bwhere\s+([A-Za-z][A-Za-z0-9_]*)\s+is\s+(\S+)",
        question, flags=re.I)
    if not explicit:
        explicit = re.findall(
            r"\bwith\s+(?!more\s+than\b)([A-Za-z][A-Za-z0-9_]*)\s+"
            r"(?!is\b|by\b|through\b)([^\s,;.]+)",
            question, flags=re.I)
    if len(explicit) > 1:
        raise ValueError("Multiple equality constraints are not supported")
    if explicit:
        property_name, literal = explicit[0]
        literal = literal.rstrip(".")
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
            bound_filter["value"] = literal
    else:
        # No user-specified scalar equality: ignore an invented model filter.
        # Verified mapping joins remain part of the selected evidence path.
        bound_filter = None
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
    if (re.search(r"\bwhere\b.+?\bis\b", question, re.I | re.S)
            or re.search(r"\bwith\s+(?!more\s+than\b)[A-Za-z][A-Za-z0-9_]*\s+\S+", question, re.I)) and bound_filter is None:
        raise ValueError("LLM omitted an explicit equality filter")
    if not paths[i]["steps"]:
        node = tuple(paths[i]["nodes"][0])
        plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "n0", "domain": node[0], "shape": node[1]}],
            "edges": [],
            "projections": [{"entity": "n0", "predicate": p["predicate"],
                             "as": p["as"]} for p in specs],
            "filters": ({"op": "eq", "entity": "n0",
                         "predicate": bound_filter["predicate"],
                         "value": bound_filter["value"]}
                        if bound_filter else None),
            "operation": {"type": expected_operation, **({"having_min": threshold} if threshold is not None else {})},
            "return_entities": False,
        }
        if order is not None:
            plan["order_by"] = order
        if result_limit is not None:
            plan["result_limit"] = result_limit
    else:
        plan = bind_evidenced_path(paths[i], catalog, mappings,
                                  projections=specs, filter_spec=bound_filter)
        plan["operation"] = {"type": expected_operation, **({"having_min": threshold} if threshold is not None else {})}
        if order is not None:
            plan["order_by"] = order
        if result_limit is not None:
            plan["result_limit"] = result_limit
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded", "choice": path_id}
