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
    # Only translate semantics supported exactly by the existing compiler.
    condition = selected["aggregate_condition"]
    if (selected.get("optional_properties", [])
            or (selected.get("distinct", False) and not selected.get("count_property"))
            or (condition is not None and condition["operator"] != "gt")
            or any(f["op"] != "eq" for f in selected["filters"])
            or len(selected["filters"]) > 1):
        raise ValueError("Semantic v2 modifier not yet supported by IR adapter")
    # An empty SELECT projection means return the evidenced entity aliases.
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
    count_property = selected.get("count_property")
    if count_property is not None:
        if selected["operation"] != "count" or not selected.get("distinct", False):
            raise ValueError("Invalid distinct count semantics")
        match = re.fullmatch(r"N(\d+)P(\d+)", count_property)
        if match is None:
            raise ValueError("Invalid distinct count property ID")
        j, k = map(int, match.groups())
        predicate = owners[tuple(path["nodes"][j])]["properties"][k]
        plan["count_distinct_property"] = {
            "entity": f"n{j}", "predicate": predicate}
    op = selected["operation"]
    plan["operation"] = {"type": op}
    if op in ("count", "group_count"):
        match = re.fullmatch(r"N(\d+)", selected["count_target"])
        if match is None or int(match.group(1)) >= len(path["nodes"]):
            raise ValueError("Invalid count target")
        plan["operation"]["count_entity"] = f"n{match.group(1)}"
    if op == "group_count" and condition is not None:
        plan["operation"]["having_min"] = condition["value"]
    if selected["filters"]:
        f = selected["filters"][0]
        match = re.fullmatch(r"N(\d+)P(\d+)", f["property"])
        if match is None:
            raise ValueError("Invalid filter property ID")
        j, k = map(int, match.groups())
        predicate = owners[tuple(path["nodes"][j])]["properties"][k]
        plan["filters"] = {"op": "eq", "entity": f"n{j}",
                           "predicate": predicate, "value": f["value"]}
    def bind_where(node):
        op = node["op"]
        if op in ("and", "or"):
            return {"op": op, "children": [
                bind_where(child) for child in node["conditions"]]}
        if op == "not":
            child = node["condition"]
            # Only negated property existence is supported by the legacy
            # compiler without altering variable scope.
            if child["op"] != "exists":
                raise ValueError("Negated condition not yet supported by IR adapter")
            return bind_where({"op": "missing", "property": child["property"]})
        if op not in ("exists", "missing", "eq", "contains", "starts_with", "regex"):
            raise ValueError("Semantic v2 condition not yet supported by IR adapter")
        if node.get("ignore_case", False) and op not in ("contains", "starts_with", "regex"):
            raise ValueError("Case-insensitive condition not supported for this operator")
        match = re.fullmatch(r"N(\d+)P(\d+)", node["property"])
        if match is None:
            raise ValueError("Invalid condition property ID")
        j, k = map(int, match.groups())
        predicate = owners[tuple(path["nodes"][j])]["properties"][k]
        result = {"op": "not_exists" if op == "missing" else op,
                  "entity": f"n{j}", "predicate": predicate}
        if op in ("eq", "contains", "starts_with", "regex"):
            result["value"] = node["value"]
        if node.get("ignore_case", False):
            result["ignore_case"] = True
        return result

    if selected.get("where") is not None:
        plan["filters"] = bind_where(selected["where"])
    if op == "select" and not selected["projections"]:
        plan["return_entities"] = True
    ordering = selected.get("order_by")
    if ordering is not None:
        if ordering["property"] not in selected["projections"]:
            raise ValueError("Order property must be projected")
        alias = f"value{selected['projections'].index(ordering['property'])}"
        plan["order_by"] = [{"as": alias, "direction": ordering["direction"]}]
    if selected.get("limit") is not None:
        plan["result_limit"] = selected["limit"]
    return resolve_shapes(plan, index, mappings=mappings), selected
