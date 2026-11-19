"""Adapter between verified legacy evidence paths and semantic selection v2.

Opt-in integration boundary: this module is not wired into the production CLI.
It never guesses missing semantics or broadens the verified candidate set.
"""
import re

from .evidence_path_binding import bind_evidenced_path
from .semantic_llm_v2 import select_semantic_v2
from .unified_answer import resolve_shapes


def _label(iri):
    local = re.split(r"[/#:]", iri)[-1]
    return local[3:] if local.lower().startswith("has") and len(local) > 3 else local


def build_v2_candidates(paths, catalog):
    """Expose stable IDs for every node and SHACL-owned property in each path."""
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ValueError("Provide 1 to 32 verified paths")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    candidates = []
    for i, path in enumerate(paths):
        nodes = path["nodes"]
        if not nodes or len(nodes) != len(path["steps"]) + 1:
            raise ValueError("Invalid evidence path")
        described_nodes = []
        properties = []
        for j, node in enumerate(nodes):
            owner = owners.get(tuple(node))
            if owner is None:
                raise ValueError("Evidence path contains unknown shape")
            described_nodes.append({
                "id": f"N{j}", "domain": owner["domain"],
                "shape": owner["display_name"]})
            for k, predicate in enumerate(owner["properties"]):
                properties.append({
                    "id": f"N{j}P{k}", "node": f"N{j}",
                    "label": _label(predicate)})
        candidates.append({
            "id": f"PATH_{i}", "nodes": described_nodes,
            "steps": path["steps"], "properties": properties})
    return candidates


def select_and_bind_v2(question, paths, catalog, index, mappings, *,
                       model, request_json, ollama_host, timeout,
                       keep_alive=None, diagnostics=None):
    """Select with the v2 LLM and bind a supported subset to Unified IR 1.0.

    Unsupported modifiers fail explicitly instead of being silently dropped.
    """
    candidates = build_v2_candidates(paths, catalog)
    selected = select_semantic_v2(
        question, candidates, model=model, request_json=request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive,
        diagnostics=diagnostics)
    i = int(selected["path_id"].split("_")[1])
    path = paths[i]
    if (selected["operation"] != "select" or selected["group_by"]
            or selected["count_target"] is not None
            or selected["aggregate_condition"] is not None
            or selected["filters"] or selected.get("where") is not None
            or selected.get("order_by") is not None
            or selected.get("limit") is not None
            or selected.get("distinct", False)
            or selected.get("optional_properties", [])):
        raise ValueError("Semantic v2 modifier not yet supported by IR adapter")
    if not selected["projections"]:
        raise ValueError("Semantic v2 SELECT requires explicit projections")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    specs = []
    for property_id in selected["projections"]:
        match = re.fullmatch(r"N(\d+)P(\d+)", property_id)
        if match is None:
            raise ValueError("Invalid selected property ID")
        node_index, property_index = map(int, match.groups())
        node = path["nodes"][node_index]
        predicate = owners[tuple(node)]["properties"][property_index]
        specs.append({"node_index": node_index, "predicate": predicate,
                      "as": f"value{len(specs)}"})
    if path["steps"]:
        plan = bind_evidenced_path(
            path, catalog, mappings, projections=specs)
    else:
        node = path["nodes"][0]
        plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "n0", "domain": node[0], "shape": node[1]}],
            "edges": [],
            "projections": [{"entity": "n0", "predicate": spec["predicate"],
                             "as": spec["as"]} for spec in specs],
            "filters": None,
            "operation": {"type": "select"},
            "return_entities": False,
        }
    return resolve_shapes(plan, index, mappings=mappings), selected
