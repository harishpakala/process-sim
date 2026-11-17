"""Evidence-gated adapter for the legacy SHACL cross-domain projection planner.

Legacy SHACL paths are candidate evidence, not permission to assert identity.
Only independently verified mapping records authorize cross-domain equality.
"""
import re
from .schema import Schema
from .semantic_planner import _candidates
from .cross_domain_projection import plan_cross_domain_projection, _same, _words
from .cross_domain_join import plan_join
from .unified_ir import validate_ir


def _legacy_question(question):
    q = question.strip().rstrip(".!?")
    patterns = [
        r"get (?P<output>\w+) from (?P<target>\w+) for (?:the )?(?P<source>\w+) (?P<entity>\w+) with (?P<filter>\w+) (?P<value>[\w.:-]+),? matched through (?P<key>\w+)",
        r"find (?P<output>\w+) from (?P<target>\w+) associated with (?P<source>\w+) (?P<entity>\w+) through (?P<key>\w+)",
        r"get (?P<output>\w+) from (?P<target>\w+) for (?P<source>\w+) (?P<entity>\w+) matched through (?P<key>\w+)",
    ]
    for i, pattern in enumerate(patterns):
        m = re.fullmatch(pattern, q, re.I)
        if m:
            f = m.groupdict()
            if i == 0:
                return "Get {output} of the {source} {entity} with {filter} {value}.".format(**f), f
            if i == 1:
                return "Find {output} associated with {source} {entity} through {key}.".format(**f), f
            return "Get {output} for the {source} {entity} matched by {key}.".format(**f), f
    return question, None


def _branch(branch, prefix, schema):
    predicates = branch["predicates"]
    paths = [h for h in schema.shacl_paths(branch["root"], max_depth=len(predicates),
                                          domain=branch["domain"])
             if [x["property"] for x in h] == predicates
             and h[-1].get("to_shape") == branch["end_shape"]
             and [e for x in h for e in x["evidence_ids"]] == branch["evidence_ids"]]
    if len(paths) != 1:
        raise ValueError("Legacy SHACL path is missing or ambiguous")
    entities = [{"alias": prefix + "0", "domain": branch["domain"], "shape": branch["root"]}]
    edges = []
    for i, hop in enumerate(paths[0], 1):
        if not hop.get("to_shape"):
            raise ValueError("Expected structural SHACL hop")
        alias = prefix + str(i)
        edges.append({"kind": "shacl", "from": entities[-1]["alias"],
                      "to": alias, "predicate": hop["property"]})
        entities.append({"alias": alias, "domain": branch["domain"],
                         "shape": hop["to_shape"]})
    return entities, edges, entities[-1]["alias"]


def _identifier_words(label):
    """Normalize identifier labels, including an optional SHACL 'has' prefix."""
    words = _words(label)
    return words[1:] if words[:1] == ["has"] else words


def plan_legacy_projection_ir(question, schema_path, mappings):
    """Translate a uniquely discovered legacy projection into validated Unified IR."""
    canonical, explicit = _legacy_question(question)
    schema = Schema(schema_path)
    catalog = _candidates(schema)
    plan = plan_cross_domain_projection(canonical, catalog, schema)
    if plan is None:
        # Consult the other legacy join planner for explicit identifier-equality
        # requests; do not silently convert its different IR shape.
        if re.search(r"\b(?:same|matching|equal|identical|sharing|shared)\b",
                     question, re.I):
            discovered = plan_join(question, catalog, schema)
            if discovered is not None:
                return _identifier_join_ir(discovered, schema, schema_path, mappings)
        return None
    source, target = plan["source"], plan["target"]
    if explicit:
        actual = {
            "source_domain": source["domain"],
            "target_domain": target["domain"],
            "join_key": plan["join_key_label"],
        }
        expected = {
            "source_domain": explicit["source"],
            "target_domain": explicit["target"],
            "join_key": explicit["key"],
        }
        if (not _same(source["domain"], explicit["source"])
                or not _same(target["domain"], explicit["target"])
                or _identifier_words(plan["join_key_label"]) != _identifier_words(explicit["key"])):
            raise ValueError(
                f"Legacy planner mismatch: expected={expected}, actual={actual}"
            )
    approved = []
    for m in mappings or []:
        if m.get("verified") is not True or not m.get("evidence_ids"):
            continue
        forward = (m.get("left_domain") == source["domain"]
                   and m.get("right_domain") == target["domain"]
                   and m.get("left_property") == source["key_predicate"]
                   and m.get("right_property") == target["key_predicate"])
        reverse = (m.get("right_domain") == source["domain"]
                   and m.get("left_domain") == target["domain"]
                   and m.get("right_property") == source["key_predicate"]
                   and m.get("left_property") == target["key_predicate"])
        if forward or reverse:
            approved.append((m, reverse))
    if len(approved) != 1:
        raise ValueError("Legacy join requires exactly one independently verified "
                         "cross-domain identifier mapping")
    m, reverse = approved[0]
    se, sedges, sa = _branch(source, "source", schema)
    te, tedges, ta = _branch(target, "target", schema)
    left, right = (ta, sa) if reverse else (sa, ta)
    lp, rp = ((target["key_predicate"], source["key_predicate"]) if reverse
              else (source["key_predicate"], target["key_predicate"]))
    filt = plan.get("filter")
    ir = {"ir_version": "1.0", "entities": se + te,
          "edges": sedges + tedges + [{"kind": "mapping", "from": left, "to": right,
                                      "mapping_id": m["id"],
                                      "left_predicate": lp, "right_predicate": rp}],
          "projections": [{"entity": ta, "predicate": plan["projection"]["predicate"],
                           "as": "value"}],
          "filters": ({"op": "eq", "entity": sa, "predicate": filt["predicate"],
                       "value": filt["value"]} if filt else None),
          "operation": {"type": "select"}, "return_entities": False}
    validate_ir(ir, schema_path, mappings=mappings)
    return ir


def _identifier_join_ir(plan, schema, schema_path, mappings):
    """Convert an unambiguous two-domain legacy identifier equality plan."""
    if plan.get("join_type") != "identifier_equality" or len(plan.get("sides", [])) != 2:
        raise ValueError("Legacy multi-domain/bridge join requires a separate IR adapter")
    first, second = plan["sides"]
    if len(first.get("branches", [])) != 1 or len(second.get("branches", [])) != 1:
        raise ValueError("Legacy identifier join has ambiguous SHACL branches")
    a, b = first["branches"][0], second["branches"][0]
    source = dict(a, domain=first["domain"])
    target = dict(b, domain=second["domain"])
    verified = []
    for m in mappings or []:
        if m.get("verified") is not True or not m.get("evidence_ids"):
            continue
        forward = (m.get("left_domain") == source["domain"]
                   and m.get("right_domain") == target["domain"]
                   and m.get("left_property") == source["key_predicate"]
                   and m.get("right_property") == target["key_predicate"])
        reverse = (m.get("right_domain") == source["domain"]
                   and m.get("left_domain") == target["domain"]
                   and m.get("right_property") == source["key_predicate"]
                   and m.get("left_property") == target["key_predicate"])
        if forward or reverse:
            verified.append((m, reverse))
    if len(verified) != 1:
        raise ValueError("Legacy identifier join requires one independently verified mapping")
    m, reverse = verified[0]
    se, sedges, sa = _branch(source, "source", schema)
    te, tedges, ta = _branch(target, "target", schema)
    left, right = (ta, sa) if reverse else (sa, ta)
    lp, rp = ((target["key_predicate"], source["key_predicate"]) if reverse
              else (source["key_predicate"], target["key_predicate"]))
    ir = {"ir_version": "1.0", "entities": se + te,
          "edges": sedges + tedges + [{
              "kind": "mapping", "from": left, "to": right,
              "mapping_id": m["id"], "left_predicate": lp, "right_predicate": rp}],
          "projections": [], "filters": None, "operation": {"type": "select"},
          "return_entities": True}
    validate_ir(ir, schema_path, mappings=mappings)
    return ir
