"""Opt-in natural-language evidence-path planning for the DTWise CLI.

Fails closed when endpoints, requirements or path selection are ambiguous.
The default generate_ir planner is not modified.
"""
import re

from .experimental_semantic_grounding import plan_single_shape_semantic
from .evidence_path_binding import bind_evidenced_path
from .evidence_path_requirements import ground_path_requirements
from .evidence_path_selection import select_evidenced_path
from .unified_answer import (
    _focused_catalog, _request_json, catalog_from_schema,
    check_semantic_coverage, enumerate_evidenced_paths, resolve_shapes,
)



def _single_shape_property(entity, name):
    """Resolve a property only from predicates owned by the selected shape."""
    matches = []
    for predicate in entity["properties"]:
        local = re.split(r"[/#]", predicate)[-1]
        names = {local.lower()}
        if local.lower().startswith("has") and len(local) > 3:
            names.add(local[3:].lower())
        if name.lower() in names:
            matches.append(predicate)
    if len(matches) != 1:
        raise ValueError("Single-shape predicate is missing or ambiguous: " + name)
    return matches[0]


def _plan_single_shape_lookup(question, catalog, mentioned, anchor, index,
                              mappings):
    """Opt-in zero-edge SELECT with an optional explicit equality filter.

    Only SHACL-owned predicates are permitted. Unsupported query syntax
    fails closed rather than silently dropping requirements.
    """
    entity = next(e for e in catalog["entities"]
                  if (e["domain"], e["shape"]) == anchor)
    label = entity["display_name"]
    pattern = (r"^\s*(?:get|show|list)\s+([A-Za-z][A-Za-z0-9_]*)"
               r"\s+from\s+" + re.escape(entity["domain"]) +
               r"\s+" + re.escape(label) +
               r"(?:\s+where\s+([A-Za-z][A-Za-z0-9_]*)\s+is\s+(\S+))?"
               r"\s*[.]?\s*$")
    match = re.fullmatch(pattern, question, re.I)
    if not match:
        raise ValueError("Unsupported single-shape query syntax")
    output_name, filter_name, filter_value = match.groups()
    output_predicate = _single_shape_property(entity, output_name)
    bound_filter = None
    if filter_name is not None:
        filter_predicate = _single_shape_property(entity, filter_name)
        # A final sentence period is punctuation, not part of the literal.
        # Keep dots and slashes inside URI values unchanged.
        value = filter_value[:-1] if filter_value.endswith(".") else filter_value
        if not value:
            raise ValueError("Empty single-shape equality value")
        bound_filter = {"op": "eq", "entity": "n0",
                        "predicate": filter_predicate, "value": value}
    plan = {
        "ir_version": "1.0",
        "entities": [{"alias": "n0", "domain": anchor[0],
                      "shape": anchor[1]}],
        "edges": [],
        "projections": [{"entity": "n0", "predicate": output_predicate,
                         "as": "value_0"}],
        "filters": bound_filter,
        "operation": {"type": "select"},
        "return_entities": False,
    }
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings)



def plan_experimental_multihop(question, index, mappings, *, model,
                               ollama_host, timeout, keep_alive=None,
                               request_json=None):
    catalog, mentioned = _focused_catalog(catalog_from_schema(index), question)
    # Named shapes are required waypoints, not necessarily path endpoints.
    # Do not guess a start/end orientation: verified mapping direction is
    # enforced by enumerate_evidenced_paths.
    anchors = []
    for entity in catalog["entities"]:
        label = entity.get("display_name")
        if not label:
            continue
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(label) + r"(?![A-Za-z0-9_])"
        if re.search(pattern, question, re.I):
            node = (entity["domain"], entity["shape"])
            if node not in anchors:
                anchors.append(node)
    if len(anchors) == 1:
        entity = next(e for e in catalog["entities"]
                      if (e["domain"], e["shape"]) == anchors[0])
        return plan_single_shape_semantic(
            question, entity, index, mappings, model=model,
            request_json=request_json or _request_json,
            ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive)
    if len(anchors) < 2:
        raise ValueError(
            "Experimental multi-hop requires at least one named SHACL shape")
    required = set(anchors)
    # Only keep paths that contain EVERY explicitly named shape. This prevents
    # silently dropping an intermediate waypoint named in the question.
    paths = []
    seen = set()
    for source in anchors:
        for target in anchors:
            if source == target:
                continue
            for path in enumerate_evidenced_paths(
                    catalog, mappings, source, target,
                    max_hops=4, max_paths=256):
                if len(path["steps"]) < 1 or not required.issubset(
                        set(path["nodes"])):
                    continue
                signature = tuple(path["nodes"]), tuple(
                    tuple(sorted(step.items())) for step in path["steps"])
                if signature not in seen:
                    seen.add(signature)
                    paths.append(path)
    if not paths:
        raise ValueError(
            "No verified multi-hop evidence path includes all named SHACL shapes")
    # Never truncate candidates silently: doing so could remove the
    # semantically correct path before the LLM can consider it.
    if len(paths) > 32:
        raise ValueError(
            "More than 32 evidenced paths; narrow the question")
    selected, selection = select_evidenced_path(
        question, paths, model=model,
        request_json=request_json or _request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive)
    if selected is None:
        raise ValueError("Experimental semantic path selection failed: " +
                         selection["status"])
    projections, filter_spec = ground_path_requirements(
        question, catalog, mentioned, selected)
    plan = bind_evidenced_path(
        selected, catalog, mappings, projections=projections,
        filter_spec=filter_spec)
    check_semantic_coverage(plan, question, catalog, mentioned)
    plan = resolve_shapes(plan, index, mappings=mappings)
    return plan, selection
