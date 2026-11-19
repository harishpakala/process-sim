"""Bounded LLM-directed exploration of verified ontology paths.

Opt-in prototype: does not alter the existing experimental multi-hop planner.
OWL labels/descriptions can be supplied as display metadata, but never count as
path evidence. Only SHACL sh:node edges and verified mappings are traversable.
"""
import json
import time

from .evidence_path_binding import bind_evidenced_path
from .unified_answer import enumerate_evidenced_paths


def _neighbors(catalog, mappings, current):
    """Offer only independently verified one-hop edges, with stable local IDs."""
    candidates = []
    for entity in catalog["entities"]:
        target = (entity["domain"], entity["shape"])
        if target == current:
            continue
        paths = enumerate_evidenced_paths(
            catalog, mappings, current, target, max_hops=1, max_paths=256)
        for path in paths:
            if len(path["steps"]) == 1:
                candidates.append(path)
    candidates.sort(key=lambda p: json.dumps(p, sort_keys=True))
    return [{"id": "EDGE_" + str(i), "path": p}
            for i, p in enumerate(candidates)]


def explore_ontology_path(question, catalog, mappings, start, end, *,
                          decide, projections, filter_spec=None,
                          max_hops=4, max_decisions=6, deadline_seconds=120):
    """Find a grounded path using LLM-directed one-hop exploration.

    The caller supplies evidenced start/end shapes and explicit projection
    requirements. `decide` receives (question, evidence) and returns
    {"action": "follow", "edge_id": "EDGE_N"} or {"action": "finish"}.
    No model-supplied IRI, mapping or projection is trusted. On success,
    return the *existing* Unified IR 1.0 plus transition diagnostics.
    """
    if not callable(decide):
        raise TypeError("decide must be callable")
    if not 1 <= max_hops <= 8 or not 1 <= max_decisions <= 20:
        raise ValueError("Invalid exploration budget")
    owners = {(e["domain"], e["shape"]) for e in catalog["entities"]}
    start, end = tuple(start), tuple(end)
    if start not in owners or end not in owners:
        raise ValueError("Start/end must be SHACL-evidenced shapes")
    if start == end:
        raise ValueError("Zero-hop exploration is not supported by this prototype")
    started = time.monotonic()
    visited = [start]
    steps = []
    trace = []
    for turn in range(max_decisions):
        if time.monotonic() - started >= deadline_seconds:
            raise ValueError("Exploration deadline exceeded")
        current = visited[-1]
        if current == end:
            # A final LLM decision is unnecessary once the supplied goal is met.
            break
        if len(steps) >= max_hops:
            raise ValueError("Hop budget exhausted before reaching target")
        options = [
            item for item in _neighbors(catalog, mappings, current)
            if tuple(item["path"]["nodes"][-1]) not in visited
        ]
        # Reassign IDs after filtering; IDs are local to this turn.
        options = [{"id": "EDGE_" + str(i), "path": item["path"]}
                   for i, item in enumerate(options)]
        if not options:
            raise ValueError("No unvisited evidenced neighbor")
        evidence = {
            "current": list(current), "goal": list(end),
            "remaining_hops": max_hops - len(steps),
            "visited": [list(n) for n in visited],
            "options": [
                {"id": o["id"], "next_shape": list(o["path"]["nodes"][-1]),
                 "step": o["path"]["steps"][0]}
                for o in options
            ],
        }
        response = decide(question, evidence)
        if not isinstance(response, dict) or response.get("action") != "follow":
            raise ValueError("LLM abstained or returned invalid exploration action")
        selected = next((o for o in options
                         if o["id"] == response.get("edge_id")), None)
        if selected is None:
            raise ValueError("LLM selected an unverified edge ID")
        path = selected["path"]
        steps.append(path["steps"][0])
        visited.append(tuple(path["nodes"][-1]))
        trace.append({"state": "FOLLOW", "edge_id": selected["id"],
                      "shape": list(visited[-1]),
                      "offered_edges": len(options)})
    if visited[-1] != end:
        raise ValueError("Decision budget exhausted before reaching target")
    # Binding re-enumerates and checks every selected SHACL/mapping edge.
    path = {"nodes": visited, "steps": steps}
    ir = bind_evidenced_path(
        path, catalog, mappings, projections=projections,
        filter_spec=filter_spec)
    return ir, {"status": "grounded", "mode": "ontology_explore",
                "decisions": len(trace), "hops": len(steps),
                "trace": trace,
                "elapsed_seconds": round(time.monotonic() - started, 3)}


def ollama_edge_decider(*, model, request_json, ollama_host,
                        timeout=60, keep_alive=None):
    """Create a deterministic JSON edge selector using the existing Ollama API."""
    def decide(question, evidence):
        payload = {
            "model": model, "stream": False, "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": (
                    "Choose exactly one next evidenced relationship toward the "
                    "question's goal. Return ONLY JSON: "
                    '{"action":"follow","edge_id":"EDGE_N"} or '
                    '{"action":"abstain"}. '
                    "Use only offered edge IDs. Never invent relationships. "
                    "Do not generate SPARQL or a new query representation."
                )},
                {"role": "user", "content": json.dumps(
                    {"question": question, "evidence": evidence},
                    separators=(",", ":"))},
            ],
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        response = request_json(
            ollama_host.rstrip("/") + "/api/chat", payload, timeout)
        try:
            return json.loads(response["message"]["content"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Ollama exploration JSON") from exc
    return decide
