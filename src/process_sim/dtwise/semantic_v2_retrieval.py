"""LLM-first retrieval of SHACL-evidenced shapes for semantic v2.

The model chooses catalog identifiers, never raw IRIs or inferred predicates.
Invalid selections fail closed after one correction attempt.
"""
import json


def retrieve_shape_nodes(question, catalog, *, model, request_json,
                         ollama_host, timeout, keep_alive=None,
                         diagnostics=None, max_nodes=8):
    entities = sorted(catalog["entities"],
                      key=lambda e: (e["domain"], e["shape"]))
    if not entities:
        raise ValueError("No evidenced shapes available")
    if len(entities) <= max_nodes:
        return [(e["domain"], e["shape"]) for e in entities]
    evidence = [{
        "id": f"S{i}", "domain": e["domain"], "shape": e["display_name"],
        "properties": [p.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                       for p in e["properties"]]}
        for i, e in enumerate(entities)]
    messages = [
        {"role": "system", "content": (
            "Select all SHACL shape IDs needed to answer the question, "
            "including intermediate relationship endpoints. Return JSON "
            "only: {\"shape_ids\":[\"S0\"]}. Choose 1 to " +
            str(max_nodes) + " IDs from the supplied catalog. Never invent IDs. "
            "If uncertain, do not guess unrelated shapes.")},
        {"role": "user", "content": json.dumps({
            "question": question, "shape_catalog": evidence}, ensure_ascii=False)},
    ]
    for attempt in (1, 2):
        payload = {"model": model, "stream": False, "format": "json",
                   "messages": list(messages), "options": {"temperature": 0}}
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        raw = request_json(ollama_host.rstrip("/") + "/api/chat",
                           payload, timeout)["message"]["content"]
        try:
            proposal = json.loads(raw)
            if not isinstance(proposal, dict) or set(proposal) != {"shape_ids"}:
                raise ValueError("Expected shape_ids only")
            ids = proposal["shape_ids"]
            if (not isinstance(ids, list) or not 1 <= len(ids) <= max_nodes
                    or any(not isinstance(x, str) or not x.startswith("S")
                           or not x[1:].isdigit() or int(x[1:]) >= len(entities)
                           or x != "S" + str(int(x[1:])) for x in ids)
                    or len(ids) != len(set(ids))):
                raise ValueError("Invalid or invented SHACL shape ID")
            if diagnostics is not None:
                diagnostics["semantic_v2_retrieval"] = {
                    "attempt": attempt, "shape_ids": ids,
                    "catalog_size": len(entities)}
            return [(entities[int(x[1:])]["domain"],
                     entities[int(x[1:])]["shape"]) for x in ids]
        except (ValueError, TypeError, KeyError) as exc:
            if attempt == 2:
                raise ValueError("Semantic v2 shape retrieval rejected after "
                                 "two attempts: " + str(exc)) from exc
            messages.extend([
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "Invalid evidence selection: " + str(exc) +
                    ". Return corrected shape_ids using only supplied IDs.")}])
    raise AssertionError("Unreachable retrieval state")
