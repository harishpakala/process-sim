"""Opt-in natural-language adapter for the bounded ontology state machine.

One LLM call grounds query endpoints and output in SHACL-owned symbols.
Subsequent calls explore one verified relationship at a time. This prototype
supports only unfiltered SELECT projections; unsupported intent fails closed.
"""
import json
import re

from .ontology_state_machine import explore_ontology_path, ollama_edge_decider
from .unified_answer import catalog_from_schema


def plan_ontology_explore(question, index, mappings, *, model,
                          ollama_host, timeout, keep_alive=None,
                          request_json=None, max_hops=4):
    from .unified_answer import _request_json
    request_json = request_json or _request_json
    catalog = catalog_from_schema(index)
    shapes = []
    shape_lookup = {}
    property_lookup = {}
    for i, entity in enumerate(catalog["entities"]):
        sid = "S" + str(i)
        shape_lookup[sid] = (entity["domain"], entity["shape"])
        props = []
        for j, predicate in enumerate(entity["properties"]):
            pid = sid + "P" + str(j)
            property_lookup[pid] = (sid, predicate)
            props.append({"id": pid, "name": re.split(r"[/#]", predicate)[-1]})
        shapes.append({"id": sid, "domain": entity["domain"],
                       "name": entity.get("display_name", ""),
                       "properties": props})
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": (
                "Ground the question to exactly one supplied SHACL output "
                "property and the source and target shapes. "
                "Return ONLY JSON with keys source, target, property, "
                "operation, filter. source and target are supplied S IDs, "
                "property is a supplied property ID owned by target. "
                "operation must be 'select' or 'unsupported'. "
                "filter must be null; if the question asks for filtering, "
                "counting, ordering, grouping, negation or multiple outputs, "
                "return operation='unsupported'. Do not invent IDs, "
                "relationships or SPARQL. For direct property retrieval, "
                "source and target must be the same shape."
            )},
            {"role": "user", "content": json.dumps(
                {"question": question, "shapes": shapes},
                separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    response = request_json(
        ollama_host.rstrip("/") + "/api/chat", payload, timeout)
    try:
        decision = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid ontology grounding JSON") from exc
    if not isinstance(decision, dict) or set(decision) != {
            "source", "target", "property", "operation", "filter"}:
        raise ValueError("Invalid ontology grounding structure")
    if decision["operation"] != "select" or decision["filter"] is not None:
        raise ValueError("Ontology exploration does not support this operation")
    source = shape_lookup.get(decision["source"])
    target = shape_lookup.get(decision["target"])
    owner = property_lookup.get(decision["property"])
    if source is None or target is None or owner is None:
        raise ValueError("LLM selected unknown SHACL symbol")
    if owner[0] != decision["target"]:
        raise ValueError("Output property is not owned by target shape")
    projection = {"predicate": owner[1], "as": "result"}
    if source == target:
        # A single shape is an evidenced zero-hop query; no path is invented.
        plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "n0", "domain": target[0],
                          "shape": target[1]}],
            "edges": [], "projections": [
                {"entity": "n0", **projection}],
            "filters": None, "operation": {"type": "select"},
            "return_entities": False,
        }
        return plan, {"status": "grounded", "mode": "ontology_explore",
                      "hops": 0, "decisions": 0}
    decider = ollama_edge_decider(
        model=model, request_json=request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive)
    return explore_ontology_path(
        question, catalog, mappings, source, target, decide=decider,
        projections=[{"node_index": -1, "predicate": owner[1],
                      "as": "result"}],
        max_hops=max_hops, deadline_seconds=timeout * (max_hops + 1))
