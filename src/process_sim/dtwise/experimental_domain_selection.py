"""LLM-first selection of domain-wide, SHACL-owned regex evidence."""
import json
import re
import time

from .experimental_evidence_selection import _label, _write_prompt_diagnostics


def select_domain_regex_plan(question, catalog, *, model, request_json,
                             ollama_host, timeout, keep_alive=None,
                             prompt_diagnostics=None):
    # Candidate discovery uses explicit domain names, not question templates.
    domains = sorted({e["domain"] for e in catalog["entities"]})
    named = [d for d in domains if re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(d) + r"(?![A-Za-z0-9_])",
        question, re.I)]
    if len(named) != 1:
        return None
    domain = named[0]
    evidence = {}
    for entity in catalog["entities"]:
        if entity["domain"] != domain:
            continue
        for predicate in entity["properties"]:
            label = _label(predicate)
            evidence.setdefault(label.casefold(), []).append(
                (entity["shape"], predicate))
    # Offer only properties explicitly named in the question, reducing
    # prompt size while leaving semantic interpretation to the LLM.
    choices = []
    for key, paths in sorted(evidence.items()):
        label = _label(paths[0][1])
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(label)
                     + r"(?![A-Za-z0-9_])", question, re.I):
            choices.append({"id": "P" + str(len(choices)),
                            "label": label, "shape_count": len(paths),
                            "key": key})
    if not choices:
        return None
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Interpret a domain-wide query using only listed SHACL property "
             "evidence. Return JSON with exactly operation, property_id, property_ids, pattern. "
             "operation is 'regex', 'has_all_properties', or 'unsupported'. For regex, select a listed "
             "property ID and copy the exact regex pattern from the question "
             "without modifying it. For has_all_properties, select two distinct listed property IDs in property_ids and set property_id and pattern to null. For regex, set property_ids to null. Do not generate SPARQL. For any other "
             "operation return unsupported with null property_id, property_ids and pattern."},
            {"role": "user", "content": json.dumps({
                "question": question, "domain": domain,
                "properties": [{"id": x["id"], "label": x["label"],
                                "shape_count": x["shape_count"]}
                               for x in choices]}, separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "stage": "experimental_domain_selection",
            "candidate_property_count": len(choices),
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
                "request_error_type": type(exc).__name__})
            _write_prompt_diagnostics(prompt_diagnostics)
        raise
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "request_status": "completed",
            "request_wall_seconds": round(time.perf_counter() - started, 3),
            "selection": choice})
        _write_prompt_diagnostics(prompt_diagnostics)
    if isinstance(choice, dict) and "property_ids" not in choice:
        choice["property_ids"] = None
    if not isinstance(choice, dict) or set(choice) != {
            "operation", "property_id", "property_ids", "pattern"}:
        raise ValueError("Invalid domain selection structure")
    if choice["operation"] == "unsupported":
        return None
    if choice["operation"] == "has_all_properties":
        ids = choice["property_ids"]
        if (not isinstance(ids, list) or len(ids) != 2
                or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != 2
                or choice["property_id"] is not None
                or choice["pattern"] is not None):
            raise ValueError("Invalid all-properties selection")
        selected_properties = []
        for prop_id in ids:
            selected = next((x for x in choices if x["id"] == prop_id), None)
            if selected is None:
                raise ValueError("Invented all-properties evidence ID")
            selected_properties.append(selected)
        # Verify the conjunctive requirement is expressed in the question.
        if not re.search(r"\b(?:both|all)\b", question, re.I):
            raise ValueError("Unrequested all-properties operation")
        plan = {
            "ir_version": "1.0", "entities": [], "edges": [],
            "projections": [], "filters": None,
            "operation": {"type": "select"}, "return_entities": True,
            "domain_both_properties": {
                "domain": domain,
                "properties": [x["label"] for x in selected_properties],
                "paths": [[list(p) for p in sorted(set(evidence[x["key"]]))]
                          for x in selected_properties]},
        }
        return plan, {"status": "evidence_semantic_grounded",
                      "choice": "VERIFIED_LLM_DOMAIN_ALL_PROPERTIES"}
    if choice["operation"] != "regex":
        raise ValueError("Unsupported domain operation")
    selected = next((x for x in choices if x["id"] == choice["property_id"]), None)
    if selected is None:
        raise ValueError("Invented domain property ID")
    pattern = choice["pattern"]
    # The LLM chooses the operation and property, but the literal regex
    # comes from the user's text. Never execute a model-edited expression.
    # Recognize the explicit regex-introducing clause, not a benchmark shape.
    expression = re.search(
        r"\bregular\s+expression\s+(.+?)\s*$", question, re.I)
    if expression is None:
        raise ValueError("Cannot identify an explicit regular expression")
    requested = expression.group(1).strip()
    if requested.endswith("?") and requested.count("?") == 1:
        requested = requested[:-1]
    if not requested:
        raise ValueError("Empty requested regular expression")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("Missing LLM-selected regular expression")
    # Reject a hallucinated expression, but normalize punctuation/anchor
    # omissions by taking the authoritative literal from the question.
    if pattern != requested:
        if prompt_diagnostics is not None:
            prompt_diagnostics["normalized_regex_from_question"] = requested
            _write_prompt_diagnostics(prompt_diagnostics)
    pattern = requested
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError("Invalid requested regular expression") from exc
    paths = sorted(set(evidence[selected["key"]]))
    plan = {
        "ir_version": "1.0", "entities": [], "edges": [],
        "projections": [], "filters": None,
        "operation": {"type": "select"}, "return_entities": True,
        "domain_regex": {"domain": domain,
                         "property": selected["label"],
                         "pattern": pattern,
                         "paths": [list(path) for path in paths]},
    }
    return plan, {"status": "evidence_semantic_grounded",
                  "choice": "VERIFIED_LLM_DOMAIN_REGEX"}
