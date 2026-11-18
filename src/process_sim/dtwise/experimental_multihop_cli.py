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




def _plan_explicit_hub_join(question, catalog, mappings, anchors, mentioned,
                            index):
    """Bind a named hub-and-spoke JOIN using only verified mapping evidence.

    This intentionally handles explicit JOIN ... THROUGH ... USING ... syntax.
    Explicit RETURN projects a SHACL-owned property; otherwise return entities.
    """
    match = re.fullmatch(
        r"\s*join\s+(.+?)\s+through\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+([A-Za-z][A-Za-z0-9_]*)\s+using\s+"
        r"([A-Za-z][A-Za-z0-9_]*(?:\s+and\s+[A-Za-z][A-Za-z0-9_]*)*)"
        r"(?:\s+where\s+([A-Za-z][A-Za-z0-9_]*)\s+is\s+(\S+?))?"
        r"(?:\s*,\s*return\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*))?"
        r"\s*[.]?\s*", question, re.I)
    if not match:
        return None
    (source_clause, hub_domain, hub_label, key_clause, filter_name,
     filter_value, output_domain, output_label, output_name) = match.groups()
    keys = {key.casefold() for key in re.split(r"\s+and\s+", key_clause, flags=re.I)}
    if keys not in ({"assetidentifier"}, {"assetidentifier", "productidentifier"}):
        raise ValueError("Unsupported explicit hub-join keys")
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    hubs = [node for node in owners
            if node[0].casefold() == hub_domain.casefold()
            and owners[node].get("display_name", "").casefold() == hub_label.casefold()]
    if len(hubs) != 1:
        raise ValueError("Explicit hub shape is missing or ambiguous")
    hub = hubs[0]
    leaves = [node for node in anchors if node != hub]
    if (len(leaves) not in (3, 4) or len(set(leaves)) != len(leaves)
            or (len(leaves) == 4 and len(keys) != 2)
            or (len(leaves) == 3 and keys != {"assetidentifier"})):
        raise ValueError("Explicit hub join requires three or four distinct named shapes")
    # Every named leaf must occur in the source clause, not merely after THROUGH.
    for node in leaves:
        entity = owners[node]
        if not re.search(r"(?<![A-Za-z0-9_])" +
                         re.escape(node[0]) + r"\s+" +
                         re.escape(entity["display_name"]) +
                         r"(?![A-Za-z0-9_])", source_clause, re.I):
            raise ValueError("Hub-join source shape is not explicitly named")
    nodes = [hub] + sorted(leaves)
    aliases = {node: "n" + str(i) for i, node in enumerate(nodes)}
    edges = []
    used_keys = set()
    for leaf in nodes[1:]:
        candidates = []
        for mapping in mappings or []:
            if mapping.get("verified") is not True or not mapping.get("evidence_ids"):
                continue
            if mapping.get("left_domain") != hub[0] or mapping.get("right_domain") != leaf[0]:
                continue
            left, right = mapping.get("left_property"), mapping.get("right_property")
            if left not in owners[hub]["properties"] or right not in owners[leaf]["properties"]:
                continue
            left_key = re.split(r"[/#]", left)[-1]
            right_key = re.split(r"[/#]", right)[-1]
            if left_key.casefold() != right_key.casefold():
                continue
            key = left_key[3:] if left_key.lower().startswith("has") else left_key
            if key.casefold() in keys:
                candidates.append((mapping, key.casefold()))
        if len(candidates) != 1:
            raise ValueError("No unique verified hub mapping for " + leaf[0])
        mapping, key = candidates[0]
        used_keys.add(key)
        edges.append({"kind": "mapping", "from": aliases[hub],
                      "to": aliases[leaf], "mapping_id": mapping["id"],
                      "left_predicate": mapping["left_property"],
                      "right_predicate": mapping["right_property"]})
    if used_keys != keys:
        raise ValueError("Not all requested hub-join keys are evidenced")
    bound_filter = None
    if filter_name is not None:
        if len(keys) != 1 or filter_name.casefold() not in keys:
            raise ValueError("Hub filter must use the single verified join key")
        predicate = _single_shape_property(owners[hub], filter_name)
        if not filter_value:
            raise ValueError("Empty hub filter value")
        bound_filter = {"op": "eq", "entity": aliases[hub],
                        "predicate": predicate, "value": filter_value}
    projections = []
    if output_domain is not None:
        targets = [node for node in leaves
                   if node[0].casefold() == output_domain.casefold()
                   and owners[node]["display_name"].casefold() == output_label.casefold()]
        if len(targets) != 1:
            raise ValueError("Hub projection target is missing or ambiguous")
        predicate = _single_shape_property(owners[targets[0]], output_name)
        projections = [{"entity": aliases[targets[0]], "predicate": predicate,
                        "as": "value_0"}]
    plan = {"ir_version": "1.0",
            "entities": [{"alias": aliases[node], "domain": node[0],
                          "shape": node[1]} for node in nodes],
            "edges": edges, "projections": projections, "filters": bound_filter,
            "operation": {"type": "select"}, "return_entities": not bool(projections)}
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded", "choice": "VERIFIED_HUB_JOIN"}



def _plan_shared_identifier_values(question, catalog, mappings, anchors,
                                   mentioned, index):
    """Ground an explicit shared-key value query without an ambiguous LLM pick."""
    match = re.fullmatch(
        r"\s*(?:list|show|get|find)\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+values\s+shared\s+by\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+and\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*[.]?\s*", question, re.I)
    if not match:
        return None
    key, first_domain, first_label, second_domain, second_label = match.groups()
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    def resolve_named(domain, label):
        found = [node for node in anchors if node[0].casefold() == domain.casefold()
                 and owners[node].get("display_name", "").casefold() == label.casefold()]
        if len(found) != 1:
            raise ValueError("Shared-key endpoint is missing or ambiguous")
        return found[0]
    start = resolve_named(first_domain, first_label)
    end = resolve_named(second_domain, second_label)
    if start == end or set(anchors) != {start, end}:
        raise ValueError("Shared-key query requires exactly two named shapes")
    candidates = []
    for path in enumerate_evidenced_paths(catalog, mappings, start, end,
                                          max_hops=1, max_paths=256):
        if len(path["steps"]) != 1 or path["steps"][0]["kind"] != "mapping":
            continue
        step = path["steps"][0]
        left, right = step["left_predicate"], step["right_predicate"]
        left_label = re.split(r"[/#]", left)[-1]
        right_label = re.split(r"[/#]", right)[-1]
        variants = {key.casefold(), ("has" + key).casefold()}
        if (left_label.casefold() in variants and
                right_label.casefold() in variants):
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError("Shared identifier has no unique verified direct mapping")
    path = candidates[0]
    predicate = path["steps"][0]["left_predicate"]
    plan = bind_evidenced_path(
        path, catalog, mappings,
        projections=[{"node_index": 0, "predicate": predicate,
                      "as": "shared_identifier"}])
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded", "choice": "VERIFIED_SHARED_IDENTIFIER"}



def _plan_filtered_cross_domain_lookup(question, catalog, mappings, anchors,
                                       mentioned, index):
    """Bind a fully specified cross-domain projection and equality constraint."""
    match = re.fullmatch(
        r"\s*(?:get|show|list)\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+for\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+where\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+is\s+(\S+?)\s*[.]?\s*",
        question, re.I)
    if not match:
        return None
    target_domain, target_label, output_name, source_domain, source_label, filter_name, value = match.groups()
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}
    def named(domain, label):
        found = [node for node in anchors if node[0].casefold() == domain.casefold()
                 and owners[node].get("display_name", "").casefold() == label.casefold()]
        if len(found) != 1:
            raise ValueError("Filtered lookup endpoint is missing or ambiguous")
        return found[0]
    target = named(target_domain, target_label)
    source = named(source_domain, source_label)
    if source == target or set(anchors) != {source, target}:
        raise ValueError("Filtered lookup requires exactly two named shapes")
    output_predicate = _single_shape_property(owners[target], output_name)
    filter_predicate = _single_shape_property(owners[source], filter_name)
    if not value:
        raise ValueError("Empty filtered lookup value")
    paths = []
    for path in enumerate_evidenced_paths(catalog, mappings, source, target,
                                          max_hops=1, max_paths=256):
        if len(path["steps"]) != 1 or path["steps"][0]["kind"] != "mapping":
            continue
        step = path["steps"][0]
        if step["left_predicate"] == filter_predicate:
            paths.append(path)
    if len(paths) != 1:
        raise ValueError("Filtered lookup has no unique verified direct mapping on filter key")
    plan = bind_evidenced_path(
        paths[0], catalog, mappings,
        projections=[{"node_index": 1, "predicate": output_predicate, "as": "value_0"}],
        filter_spec={"node_index": 0, "predicate": filter_predicate,
                     "op": "eq", "value": value})
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded", "choice": "VERIFIED_FILTERED_LOOKUP"}


def plan_experimental_multihop(question, index, mappings, *, model,
                               ollama_host, timeout, keep_alive=None,
                               request_json=None):
    """One LLM selection for zero-edge, direct, and multi-hop evidence."""
    from .experimental_evidence_selection import select_evidence_plan

    # Keep the full catalog for cross-domain target discovery. A question may
    # name DEXPI explicitly while requesting a property owned by OPCUA.
    catalog = catalog_from_schema(index)
    _, mentioned = _focused_catalog(catalog, question)

    def mentioned_name(name):
        # Only a terminal plural "s" is normalized; never use fuzzy matching.
        names = {name.casefold()}
        if name.lower().endswith("s"):
            names.add(name[:-1].casefold())
        else:
            names.add((name + "s").casefold())
        return any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(n)
                             + r"(?![A-Za-z0-9_])", question, re.I)
                   for n in names if n)

    anchors = []
    for entity in catalog["entities"]:
        label = entity.get("display_name")
        if label and mentioned_name(label):
            node = (entity["domain"], entity["shape"])
            if node not in anchors:
                anchors.append(node)
    if not anchors:
        raise ValueError("Experimental planner requires a named SHACL shape")
    hub_join = _plan_explicit_hub_join(question, catalog, mappings, anchors,
                                       mentioned, index)
    if hub_join is not None:
        return hub_join

    shared = _plan_shared_identifier_values(question, catalog, mappings,
                                            anchors, mentioned, index)
    if shared is not None:
        return shared

    filtered = _plan_filtered_cross_domain_lookup(question, catalog, mappings,
                                                  anchors, mentioned, index)
    if filtered is not None:
        return filtered

    # An explicitly requested output can identify an unnamed target shape.
    # Consider only properties in the output clause, not join keys after
    # "through"/"via"/"using" or entity mentions after "associated with".
    output_clause = re.split(
        r"\b(?:associated\s+with|through|via|using|where)\b",
        question, maxsplit=1, flags=re.I)[0]
    requested_owners = set()
    for entity in catalog["entities"]:
        for predicate in entity["properties"]:
            local = re.split(r"[/#]", predicate)[-1]
            names = {local}
            if local.lower().startswith("has") and len(local) > 3:
                names.add(local[3:])
            if any(re.search(
                    r"(?<![A-Za-z0-9_])" + re.escape(name) + r"s?(?![A-Za-z0-9_])",
                    output_clause, re.I) for name in names):
                requested_owners.add((entity["domain"], entity["shape"]))

    if requested_owners and not requested_owners.intersection(anchors):
        # Only infer a target when exactly one property-owning shape has
        # verified connectivity to an explicitly named anchor.
        reachable = set()
        for owner in requested_owners:
            for anchor in anchors:
                if enumerate_evidenced_paths(
                        catalog, mappings, anchor, owner,
                        max_hops=4, max_paths=1):
                    reachable.add(owner)
                    break
        if len(reachable) != 1:
            raise ValueError(
                "Requested output property has no unique verified target shape")
        target = next(iter(reachable))
        if target not in anchors:
            anchors.append(target)
    if len(anchors) == 1:
        paths = [{"nodes": [anchors[0]], "steps": []}]
    else:
        required = set(anchors)
        paths = []
        seen = set()
        for source in anchors:
            for target in anchors:
                if source == target:
                    continue
                for path in enumerate_evidenced_paths(
                        catalog, mappings, source, target,
                        max_hops=4, max_paths=256):
                    if not required.issubset(set(path["nodes"])):
                        continue
                    signature = (tuple(path["nodes"]), tuple(
                        tuple(sorted(step.items())) for step in path["steps"]))
                    if signature not in seen:
                        seen.add(signature)
                        paths.append(path)
        if not paths:
            raise ValueError(
                "No verified evidence path includes all named SHACL shapes")
    if len(paths) > 32:
        raise ValueError("More than 32 evidenced paths; narrow the question")
    plan, selection = select_evidence_plan(
        question, paths, catalog, index, mappings, model=model,
        request_json=request_json or _request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive)
    check_semantic_coverage(plan, question, catalog, mentioned)
    return plan, selection
