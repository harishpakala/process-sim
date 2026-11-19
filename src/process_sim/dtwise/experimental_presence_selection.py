"""LLM-first selection of SHACL-grounded property presence and absence."""
import json
import re
from .experimental_evidence_selection import _label, _write_prompt_diagnostics
from .unified_answer import resolve_shapes


def select_presence_plan(question, anchor, catalog, index, mappings, *,
                         model, request_json, ollama_host, timeout,
                         keep_alive=None, prompt_diagnostics=None):
    # Only consider questions with an explicit absence cue. Positive-only
    # selection remains in the existing general evidence selector.
    if not re.search(r"\b(?:no|without|missing|absent|lacking)\b", question, re.I):
        return None
    entity = next((e for e in catalog["entities"]
                   if (e["domain"], e["shape"]) == anchor), None)
    if entity is None:
        return None
    choices = []
    for predicate in entity["properties"]:
        label = _label(predicate)
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(label)
                     + r"(?![A-Za-z0-9_])", question, re.I):
            choices.append({"id": "P" + str(len(choices)),
                            "label": label, "predicate": predicate})
    if not choices:
        return None
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Select a property-presence query only if the user asks for "
             "entities having some properties and lacking other properties. "
             "Return JSON with exactly operation, present_ids, absent_ids. "
             "operation is 'presence' or 'unsupported'. Select property IDs "
             "only from the supplied SHACL evidence. An absent property is "
             "not an equality filter with null. For unsupported return "
             "empty arrays. Do not generate SPARQL."},
            {"role": "user", "content": json.dumps({
                "question": question,
                "domain": anchor[0], "shape": entity.get("display_name", anchor[1]),
                "properties": [{"id": x["id"], "label": x["label"]}
                               for x in choices]}, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "stage": "experimental_presence_selection",
            "candidate_property_count": len(choices),
            "request_status": "started"})
        _write_prompt_diagnostics(prompt_diagnostics)
    response = request_json(ollama_host.rstrip("/") + "/api/chat",
                            payload, timeout)
    try:
        choice = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid presence-selection JSON") from exc
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "request_status": "completed", "selection": choice})
        _write_prompt_diagnostics(prompt_diagnostics)
    if not isinstance(choice, dict) or set(choice) != {
            "operation", "present_ids", "absent_ids"}:
        raise ValueError("Invalid presence selection structure")
    if choice["operation"] == "unsupported":
        return None
    if choice["operation"] != "presence":
        raise ValueError("Unsupported presence operation")
    positive, negative = choice["present_ids"], choice["absent_ids"]
    valid = {x["id"]: x for x in choices}
    if (not isinstance(positive, list) or not isinstance(negative, list)
            or not positive or not negative
            or any(not isinstance(x, str) or x not in valid
                   for x in positive + negative)
            or len(set(positive + negative)) != len(positive + negative)):
        raise ValueError("Invalid or invented presence evidence IDs")
    leaves = [{"entity": "n0", "predicate": valid[x]["predicate"], "op": op}
              for op, ids in (("exists", positive), ("not_exists", negative))
              for x in ids]
    plan = {
        "ir_version": "1.0",
        "entities": [{"alias": "n0", "domain": anchor[0], "shape": anchor[1]}],
        "edges": [], "projections": [],
        "filters": {"op": "and", "children": leaves},
        "operation": {"type": "select"}, "return_entities": True,
    }
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_LLM_PROPERTY_PRESENCE"}
