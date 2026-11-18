"""Opt-in natural-language evidence-path planning for the DTWise CLI.

Fails closed when endpoints, requirements or path selection are ambiguous.
The default generate_ir planner is not modified.
"""
import re

from .evidence_path_binding import bind_evidenced_path
from .evidence_path_requirements import ground_path_requirements
from .evidence_path_selection import select_evidenced_path
from .unified_answer import (
    _focused_catalog, _request_json, catalog_from_schema,
    check_semantic_coverage, enumerate_evidenced_paths, resolve_shapes,
)


def plan_experimental_multihop(question, index, mappings, *, model,
                               ollama_host, timeout, keep_alive=None,
                               request_json=None):
    catalog, mentioned = _focused_catalog(catalog_from_schema(index), question)
    # Require exactly two explicit, uniquely identifiable endpoint shapes.
    # Other shapes may still appear as intermediate nodes.
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
    if len(anchors) != 2 or anchors[0] == anchors[1]:
        raise ValueError("Experimental multi-hop requires exactly two unambiguous named SHACL endpoint shapes")
    # Enumerate both orientations; mappings remain strictly directional.
    paths = []
    for source, target in ((anchors[0], anchors[1]),
                           (anchors[1], anchors[0])):
        paths.extend(enumerate_evidenced_paths(
            catalog, mappings, source, target, max_hops=4, max_paths=32))
    # The experimental route is for actual multi-hop paths only.
    paths = [p for p in paths if len(p["steps"]) >= 2][:32]
    if not paths:
        raise ValueError("No verified multi-hop evidence path connects the named shapes")
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
