"""One-call, SHACL-constrained semantic grounding for experimental DTWise planning.

The model may choose only catalog identifiers; Python owns IR construction.
"""
import json
import re

from .unified_answer import resolve_shapes


def _label(iri):
    local = re.split(r"[/#]", iri)[-1]
    return local[3:] if local.lower().startswith("has") and len(local) > 3 else local


def plan_single_shape_semantic(question, entity, index, mappings, *,
                               model, request_json, ollama_host, timeout,
                               keep_alive=None):
    """Interpret a single-domain question in one LLM call, then verify all IDs.

    Supports SELECT with one or more projections and optional scalar equality.
    Other operations fail closed until the IR/compiler supports them.
    """
    predicates = list(entity["properties"])
    candidates = [{"id": "P" + str(i), "label": _label(p),
                   "predicate": p} for i, p in enumerate(predicates)]
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Interpret the question using ONLY the supplied SHACL property IDs. "
             "Return JSON with keys operation, projections, filter. "
             "operation must be 'select' or 'unsupported'. "
             "projections must be an array of property IDs (e.g. ['P0']). "
             "filter must be null or {property: 'P0', op: 'eq', value: 'literal'}. "
             "Never drop requested requirements. Use unsupported for count, "
             "grouping, sorting, limits, ambiguous intent, or ungrounded properties. "
             "Never invent a property ID. Do not return SPARQL."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "entity": {"domain": entity["domain"],
                           "shape": entity["shape"],
                           "label": entity["display_name"]},
                "properties": candidates,
            }, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    response = request_json(ollama_host.rstrip("/") + "/api/chat",
                            payload, timeout)
    raw = response.get("message", {}).get("content", "")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid semantic-planning JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {
            "operation", "projections", "filter"}:
        raise ValueError("Invalid semantic-planning response structure")
    if parsed["operation"] != "select":
        raise ValueError("Unsupported semantic-planning operation")
    selected = parsed["projections"]
    lookup = {c["id"]: c["predicate"] for c in candidates}
    if (not isinstance(selected, list) or not selected or
            any(not isinstance(p, str) or p not in lookup for p in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("Missing, repeated, or invented projection ID")
    bound_filter = None
    spec = parsed["filter"]
    if spec is not None:
        if (not isinstance(spec, dict) or set(spec) != {"property", "op", "value"}
                or spec["property"] not in lookup or spec["op"] != "eq"
                or type(spec["value"]) not in (str, int, float, bool)):
            raise ValueError("Invalid or unsupported semantic filter")
        bound_filter = {"op": "eq", "entity": "n0",
                        "predicate": lookup[spec["property"]],
                        "value": spec["value"]}
    # A missing equality filter is never acceptable when the question
    # explicitly contains an equality clause.
    if re.search(r"\bwhere\b.+?\bis\b", question, re.I | re.S) and bound_filter is None:
        raise ValueError("LLM omitted an explicit equality filter")
    plan = {
        "ir_version": "1.0",
        "entities": [{"alias": "n0", "domain": entity["domain"],
                      "shape": entity["shape"]}],
        "edges": [],
        "projections": [{"entity": "n0", "predicate": lookup[p],
                         "as": "value_" + str(i)}
                        for i, p in enumerate(selected)],
        "filters": bound_filter,
        "operation": {"type": "select"},
        "return_entities": False,
    }
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "single_shape_llm_grounded", "choice": None}
