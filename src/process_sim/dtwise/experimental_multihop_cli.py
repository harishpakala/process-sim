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


def _plan_named_substring_lookup(question, catalog, mentioned, anchors,
                                 index, mappings):
    """Ground an explicitly named shape and substring property without an LLM."""
    match = re.fullmatch(
        r"\s*which\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+entities\s+have\s+an?\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+containing\s+"
        r"([A-Za-z0-9][A-Za-z0-9_-]*)(,\s*ignoring\s+case)?\s*\?\s*", question, re.I)
    if not match:
        return None
    domain, label, property_name, literal, ignoring_case = match.groups()
    matches = [e for e in catalog["entities"]
               if e["domain"].casefold() == domain.casefold()
               and e.get("display_name", "").casefold() == label.casefold()]
    if len(matches) != 1:
        raise ValueError("Substring lookup requires one named SHACL shape")
    entity = matches[0]
    anchor = (entity["domain"], entity["shape"])
    if set(anchors) != {anchor}:
        raise ValueError("Substring lookup requires one unambiguous named shape")
    predicate = _single_shape_property(entity, property_name)
    plan = {
        "ir_version": "1.0",
        "entities": [{"alias": "n0", "domain": anchor[0], "shape": anchor[1]}],
        "edges": [],
        "projections": [{"entity": "n0", "predicate": predicate,
                         "as": "value_0"}],
        "filters": {"op": "contains", "entity": "n0",
                    "predicate": predicate, "value": literal,
                    **({"ignore_case": True} if ignoring_case else {})},
        "operation": {"type": "select"},
        "return_entities": True,
    }
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_NAMED_SUBSTRING_LOOKUP"}


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
        # Manifest B19: "For DOMAIN Shape entities where Key is VALUE, list Field."
        # Match the complete question to avoid silently ignoring constraints.
        alternate = (r"^\s*for\s+" + re.escape(entity["domain"]) +
                     r"\s+" + re.escape(label) +
                     r"\s+entities\s+where\s+([A-Za-z][A-Za-z0-9_]*)" +
                     r"\s+is\s+(\S+?)\s*,\s*list\s+" +
                     r"([A-Za-z][A-Za-z0-9_]*)\s*[.]?\s*$")
        alternate_match = re.fullmatch(alternate, question, re.I)
        if not alternate_match:
            raise ValueError("Unsupported single-shape query syntax")
        filter_name, filter_value, output_name = alternate_match.groups()
        match_groups = (output_name, filter_name, filter_value)
    else:
        match_groups = match.groups()
    output_name, filter_name, filter_value = match_groups
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
        r"(?:\s*,\s*return\s+(.+?))?"
        r"\s*[.]?\s*", question, re.I)
    if not match:
        return None
    (source_clause, hub_domain, hub_label, key_clause, filter_name,
     filter_value, output_clause) = match.groups()
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
    if output_clause is not None:
        # Each requested output is a fully qualified Domain Shape Property.
        # Reject any partial clause rather than silently dropping a projection.
        clauses = re.split(r"\s+and\s+", output_clause, flags=re.I)
        if not clauses or len(clauses) > len(leaves):
            raise ValueError("Unsupported hub projection list")
        seen = set()
        for i, clause in enumerate(clauses):
            output_match = re.fullmatch(
                r"([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*)"
                r"\s+([A-Za-z][A-Za-z0-9_]*)", clause.strip(), re.I)
            if not output_match:
                raise ValueError("Invalid qualified hub projection")
            output_domain, output_label, output_name = output_match.groups()
            targets = [node for node in leaves
                       if node[0].casefold() == output_domain.casefold()
                       and owners[node]["display_name"].casefold() == output_label.casefold()]
            if len(targets) != 1:
                raise ValueError("Hub projection target is missing or ambiguous")
            predicate = _single_shape_property(owners[targets[0]], output_name)
            if (targets[0], predicate) in seen:
                raise ValueError("Duplicate hub projection")
            seen.add((targets[0], predicate))
            projections.append({"entity": aliases[targets[0]], "predicate": predicate,
                                "as": "value_" + str(i)})
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



def _plan_named_direct_mapping_lookup(question, catalog, mappings, anchors,
                                      mentioned, index):
    """Bind an explicit two-shape projection through a named verified mapping."""
    match = re.fullmatch(
        r"\s*find\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*)"
        r"\s+associated\s+with\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+through\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*[.]?\s*", question, re.I)
    if not match:
        return None
    target_domain, target_label, output_name, source_domain, source_label, join_name = match.groups()
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}

    def named(domain, label):
        matches = [node for node in anchors
                   if node[0].casefold() == domain.casefold()
                   and owners[node]["display_name"].casefold() == label.casefold()]
        if len(matches) != 1:
            raise ValueError("Named mapping lookup endpoint missing or ambiguous")
        return matches[0]

    target, source = named(target_domain, target_label), named(source_domain, source_label)
    if source == target or set(anchors) != {source, target}:
        raise ValueError("Named mapping lookup requires exactly two shapes")
    output_predicate = _single_shape_property(owners[target], output_name)
    source_key = _single_shape_property(owners[source], join_name)
    target_key = _single_shape_property(owners[target], join_name)
    paths = [
        path for path in enumerate_evidenced_paths(
            catalog, mappings, source, target, max_hops=1, max_paths=256)
        if len(path["steps"]) == 1
        and path["steps"][0]["kind"] == "mapping"
        and path["steps"][0]["left_predicate"] == source_key
        and path["steps"][0]["right_predicate"] == target_key
    ]
    if len(paths) != 1:
        raise ValueError("No unique verified direct mapping for named join key")
    plan = bind_evidenced_path(
        paths[0], catalog, mappings,
        projections=[{"node_index": 1, "predicate": output_predicate,
                      "as": "value_0"}])
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_NAMED_DIRECT_MAPPING_LOOKUP"}



def _plan_named_identifier_anti_join(question, catalog, mappings, anchors,
                                     mentioned, index):
    """Ground a two-shape negative match using an exact verified mapping."""
    match = re.fullmatch(
        r"\s*which\s+([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+entities\s+have\s+no\s+matching\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+by\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*\?\s*", question, re.I)
    if not match:
        return None
    source_domain, source_label, target_domain, target_label, key_name = match.groups()
    owners = {(e["domain"], e["shape"]): e for e in catalog["entities"]}

    def named(domain, label):
        found = [node for node in anchors
                 if node[0].casefold() == domain.casefold()
                 and owners[node]["display_name"].casefold() == label.casefold()]
        if len(found) != 1:
            raise ValueError("Anti-join endpoint is missing or ambiguous")
        return found[0]

    source, target = named(source_domain, source_label), named(target_domain, target_label)
    if source == target or set(anchors) != {source, target}:
        raise ValueError("Anti-join requires exactly two named shapes")
    source_key = _single_shape_property(owners[source], key_name)
    target_key = _single_shape_property(owners[target], key_name)
    paths = [
        path for path in enumerate_evidenced_paths(
            catalog, mappings, source, target, max_hops=1, max_paths=256)
        if len(path["steps"]) == 1
        and path["steps"][0]["kind"] == "mapping"
        and path["steps"][0]["left_predicate"] == source_key
        and path["steps"][0]["right_predicate"] == target_key
    ]
    if len(paths) != 1:
        raise ValueError("Anti-join requires one unique verified direct mapping")
    plan = bind_evidenced_path(
        paths[0], catalog, mappings,
        projections=[{"node_index": 0, "predicate": source_key,
                      "as": "verified_key"}])
    # The projection was only used to validate ownership; anti-join returns
    # the source entity, not its key.
    plan["projections"] = []
    plan["return_entities"] = True
    plan["anti_join"] = {"from": "n0", "to": "n1"}
    check_semantic_coverage(plan, question, catalog, mentioned)
    return resolve_shapes(plan, index, mappings=mappings), {
        "status": "evidence_semantic_grounded",
        "choice": "VERIFIED_IDENTIFIER_ANTI_JOIN"}


def _plan_domain_both_properties(question, catalog):
    """Find same-domain entities with both evidenced predicates."""
    match = re.fullmatch(
        r"\s*which\s+([A-Za-z][A-Za-z0-9_]*)\s+entities\s+have\s+both\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+and\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s*\?\s*", question, re.I)
    if not match:
        return None
    domain, left_name, right_name = match.groups()
    candidates = [e for e in catalog["entities"]
                  if e["domain"].casefold() == domain.casefold()]
    if not candidates:
        raise ValueError("Unknown domain for both-property lookup")
    def paths(name):
        return sorted({(e["shape"], predicate)
                       for e in candidates for predicate in e["properties"]
                       if re.split(r"[/#]", predicate)[-1].casefold()
                       in {name.casefold(), ("has" + name).casefold()}})
    left, right = paths(left_name), paths(right_name)
    if not left or not right or left_name.casefold() == right_name.casefold():
        raise ValueError("Both requested properties require distinct evidenced predicates")
    plan = {
        "ir_version": "1.0", "entities": [], "edges": [],
        "projections": [], "filters": None,
        "operation": {"type": "select"}, "return_entities": True,
        "domain_both_properties": {
            "domain": candidates[0]["domain"],
            "properties": [left_name, right_name],
            "paths": [[list(p) for p in left], [list(p) for p in right]]},
    }
    return plan, {"status": "evidence_semantic_grounded",
                  "choice": "VERIFIED_DOMAIN_BOTH_PROPERTIES"}


def _plan_domain_regex_lookup(question, catalog, mentioned):
    """Match domain-wide regex requests against all evidenced property owners."""
    match = re.fullmatch(
        r"\s*which\s+([A-Za-z][A-Za-z0-9_]*)\s+entities\s+have\s+a\s+"
        r"([A-Za-z][A-Za-z0-9_]*)\s+matching\s+the\s+regular\s+expression\s+"
        r"([^\s]+)\s*", question, re.I)
    if not match:
        return None
    domain, property_name, pattern = match.groups()
    import re as _re
    try:
        _re.compile(pattern)
    except _re.error as exc:
        raise ValueError("Invalid requested regular expression") from exc
    candidates = [e for e in catalog["entities"]
                  if e["domain"].casefold() == domain.casefold()]
    if not candidates:
        raise ValueError("Unknown domain for regex lookup")
    paths = sorted({(e["shape"], predicate)
                    for e in candidates for predicate in e["properties"]
                    if (re.split(r"[/#]", predicate)[-1].casefold()
                        in {property_name.casefold(),
                            ("has" + property_name).casefold()})})
    if not paths:
        raise ValueError("No evidenced domain property for regex lookup")
    plan = {
        "ir_version": "1.0", "entities": [], "edges": [],
        "projections": [], "filters": None,
        "operation": {"type": "select"}, "return_entities": True,
        "domain_regex": {"domain": candidates[0]["domain"],
                         "property": property_name,
                         "pattern": pattern,
                         "paths": [list(path) for path in paths]},
    }
    return plan, {"status": "evidence_semantic_grounded",
                  "choice": "VERIFIED_DOMAIN_REGEX_LOOKUP"}


def plan_experimental_multihop(question, index, mappings, *, model,
                               ollama_host, timeout, keep_alive=None,
                               request_json=None, prompt_diagnostics=None,
                               planning_mode='hybrid'):
    """Plan using LLM evidence selection or opt-in legacy template shortcuts."""
    if planning_mode not in ('hybrid', 'llm_first', 'semantic_v2'):
        raise ValueError('Unsupported experimental planning mode')
    from .experimental_evidence_selection import select_evidence_plan

    # Keep the full catalog for cross-domain target discovery. A question may
    # name DEXPI explicitly while requesting a property owned by OPCUA.
    catalog = catalog_from_schema(index)
    if planning_mode == 'semantic_v2':
        # No question-text regex or deterministic NL interpretation in this
        # branch: the LLM chooses among SHACL-evidenced path candidates.
        from .semantic_v2_adapter import select_and_bind_v2
        nodes = sorted({(entity["domain"], entity["shape"])
                        for entity in catalog["entities"]})
        paths = [{"nodes": [node], "steps": []} for node in nodes]
        seen = {(tuple(path["nodes"]), ()) for path in paths}
        for source in nodes:
            for target in nodes:
                if source == target:
                    continue
                for path in enumerate_evidenced_paths(
                        catalog, mappings, source, target,
                        max_hops=4, max_paths=256):
                    signature = (tuple(path["nodes"]), tuple(
                        tuple(sorted(step.items())) for step in path["steps"]))
                    if signature not in seen:
                        seen.add(signature)
                        paths.append(path)
                    if len(paths) > 32:
                        raise ValueError(
                            "Semantic v2 candidate limit exceeded; "
                            "narrow the evidence catalog")
        return select_and_bind_v2(
            question, paths, catalog, index, mappings, model=model,
            request_json=request_json or _request_json,
            ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive,
            diagnostics=prompt_diagnostics)
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
    if planning_mode == 'hybrid':
        domain_both = _plan_domain_both_properties(question, catalog)
        if domain_both is not None:
            return domain_both

        domain_regex = _plan_domain_regex_lookup(question, catalog, mentioned)
        if domain_regex is not None:
            return domain_regex

        substring = _plan_named_substring_lookup(
            question, catalog, mentioned, anchors, index, mappings)
        if substring is not None:
            return substring

        anti_join = _plan_named_identifier_anti_join(
            question, catalog, mappings, anchors, mentioned, index)
        if anti_join is not None:
            return anti_join

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

        named_mapping = _plan_named_direct_mapping_lookup(
            question, catalog, mappings, anchors, mentioned, index)
        if named_mapping is not None:
            return named_mapping

        # Handle the fully specified single-shape B19 lookup before inferring
        # cross-domain output owners from incidental words in the filter clause.
        if len(anchors) == 1 and re.match(r"^\s*for\s+", question, re.I):
            plan = _plan_single_shape_lookup(
                question, catalog, mentioned, anchors[0], index, mappings)
            return plan, {"status": "evidence_semantic_grounded",
                          "choice": "VERIFIED_SINGLE_SHAPE_LOOKUP"}


    if not anchors:
        from .experimental_domain_selection import select_domain_regex_plan
        domain_plan = select_domain_regex_plan(
            question, catalog, model=model,
            request_json=request_json or _request_json,
            ollama_host=ollama_host, timeout=timeout,
            keep_alive=keep_alive, prompt_diagnostics=prompt_diagnostics)
        if domain_plan is not None:
            return domain_plan
        raise ValueError('No evidenced domain-wide LLM plan for this question')

    if len(anchors) == 1:
        from .experimental_presence_selection import select_presence_plan
        presence = select_presence_plan(
            question, anchors[0], catalog, index, mappings, model=model,
            request_json=request_json or _request_json,
            ollama_host=ollama_host, timeout=timeout,
            keep_alive=keep_alive, prompt_diagnostics=prompt_diagnostics)
        if presence is not None:
            plan, selection = presence
            check_semantic_coverage(plan, question, catalog, mentioned)
            return plan, selection

    # Two explicitly named shapes: a compact, operation-aware LLM decision
    # avoids exposing the entire property catalog for entity-return joins.
    if len(anchors) == 2:
        from .experimental_relation_selection import select_evidence_relation
        relation = select_evidence_relation(
            question, anchors, catalog, index, mappings, model=model,
            request_json=request_json or _request_json,
            ollama_host=ollama_host, timeout=timeout,
            keep_alive=keep_alive, prompt_diagnostics=prompt_diagnostics)
        if relation is not None:
            plan, selection = relation
            check_semantic_coverage(plan, question, catalog, mentioned)
            return plan, selection

    # An explicitly requested output can identify an unnamed target shape.
    # Consider only properties in the output clause, not join keys after
    # "through"/"via"/"using" or entity mentions after "associated with".
    # Prefer an explicit trailing output command over the leading WHERE
    # clause (e.g. "For Shape where Key is X, list Field").
    output_commands = list(re.finditer(
        r"\b(?:list|show|return|display|get)\s+",
        question, re.I))
    if output_commands:
        output_clause = question[output_commands[-1].end():]
    else:
        output_clause = re.split(
            r"\b(?:associated\s+with|through|via|using|where)\b",
            question, maxsplit=1, flags=re.I)[0]
        # A JOIN statement declares entity participants and join keys, not
        # output properties. Without an explicit projection clause there is
        # no property owner to infer.
        if re.match(r"^\s*join\b", question, re.I):
            output_clause = ""
    # A count of named entities requests an aggregate, not a property projection.
    # Do not infer extra target shapes from incidental property-name matches.
    is_entity_count = bool(re.match(
        r"^\s*(?:count|how\s+many)\b", question, re.I)) and not re.search(
            r"\b(?:return|show|list)\b", question, re.I)
    requested_owners = set()
    for entity in ([] if is_entity_count else catalog["entities"]):
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
            # A connected join graph need not be representable as a linear
            # path. Let the LLM choose only preverified mapping-edge IDs.
            from .experimental_subgraph_selection import select_evidence_subgraph
            plan, selection = select_evidence_subgraph(
                question, anchors, catalog, index, mappings, model=model,
                request_json=request_json or _request_json,
                ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive,
                prompt_diagnostics=prompt_diagnostics)
            check_semantic_coverage(plan, question, catalog, mentioned)
            return plan, selection
    if len(paths) > 32:
        raise ValueError("More than 32 evidenced paths; narrow the question")
    plan, selection = select_evidence_plan(
        question, paths, catalog, index, mappings, model=model,
        request_json=request_json or _request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive,
        prompt_diagnostics=prompt_diagnostics)
    check_semantic_coverage(plan, question, catalog, mentioned)
    return plan, selection
