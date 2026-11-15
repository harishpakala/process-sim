"""Schema-grounded two-key, three-domain entity projection joins.

No domain names, identifier names, or RDF predicates are embedded here.
The intermediate domain is discovered from SHACL terminal-property evidence.
"""
import re
from process_sim.dtwise.cross_domain_join import _mentioned
from process_sim.dtwise.query_planner import validate_hops


def _properties(candidate):
    return {label: p for p in candidate["terminal"]
            for label in p["labels"] if not label.startswith("has")
            and validate_hops([p["_hop"]], candidate["_schema"], candidate["end"])}


def _identifiers(props):
    return {name for name in props if name.casefold().endswith("identifier")}


def _choose(options, role):
    unique = {}
    for c, props in options:
        signature = (c["domain"], c["root"], tuple(c["predicates"]), c["end"])
        unique[signature] = (c, props)
    if not unique:
        return None
    shortest = min(len(c["predicates"]) for c, _ in unique.values())
    finalists = [(c, p) for c, p in unique.values()
                 if len(c["predicates"]) == shortest]
    if len(finalists) != 1:
        raise ValueError("Ambiguous SHACL paths for " + role)
    return finalists[0]


def plan_multihop_projection(question, catalog, schema):
    """Return a verified three-domain, two-identifier plan, or None."""
    if not re.search(r"\b(?:associated|used|belong|linked|corresponding|matching|connected|related|traced|mapped|via|through)\b",
                     question, re.I):
        return None
    prepared = []
    for candidate in catalog:
        if not validate_hops(candidate["_hops"], schema, candidate["root"]):
            continue
        c = dict(candidate, _schema=schema)
        prepared.append((c, _properties(c)))
    explicit_domains = {c["domain"] for c, _ in prepared
                        if _mentioned(c["domain"], question)}
    if len(explicit_domains) > 2:
        return None
    # Entity labels can identify a source even when its domain name is omitted.
    # Require an unambiguous source domain and a distinct output entity; never
    # infer a relationship solely from coincidentally shared property names.
    entity_mentions = [(c, p) for c, p in prepared
                       if any(_mentioned(label, question) for label in c["target_labels"]
                              if not label.endswith(("SHACL shape", "constraint")))]
    source_domains = {c["domain"] for c, _ in entity_mentions
                      if c["domain"] in explicit_domains}
    if not source_domains and len({c["domain"] for c, _ in entity_mentions}) == 2:
        # Without a domain anchor the direction is not grounded.
        return None
    sources = [(c, p) for c, p in entity_mentions
               if c["domain"] in source_domains]
    if not sources:
        return None
    # A single output property is sufficient only when the target entity is
    # explicitly mentioned and the SHACL-grounded route is unique.
    outputs_by_domain = {}
    for c, props in prepared:
        named = {label for label in props if _mentioned(label, question)}
        if named:
            outputs_by_domain.setdefault(c["domain"], []).append((c, props, named))
    targets = [(domain, entries) for domain, entries in outputs_by_domain.items()
               if domain not in {c["domain"] for c, _ in sources}]
    # A bridge entity may expose an identifier also requested on the output
    # entity (e.g. ProductIdentifier on both Asset and Product). Do not
    # interpret that shared join key as a second requested output domain.
    # Prefer the unique explicitly named entity with the most requested
    # terminal properties; ties remain unresolved rather than guessed.
    scored_targets = []
    for domain, entries in targets:
        matching = [(c, props, named) for c, props, named in entries
                    if any(_mentioned(label, question) for label in c["target_labels"])]
        if matching:
            score = max(len(named) for _, _, named in matching)
            scored_targets.append((score, domain, matching))
    if not scored_targets:
        return None
    highest = max(score for score, _, _ in scored_targets)
    winners = [(domain, entries) for score, domain, entries in scored_targets
               if score == highest]
    if len(winners) != 1:
        return None
    target_domain, target_entries = winners[0]
    # All requested output properties must belong to one SHACL entity.
    target_options = [(c, p) for c, p, named in target_entries
                      if any(_mentioned(label, question) for label in c["target_labels"])]
    if not target_options:
        return None
    target = _choose(target_options, "output entity")
    if target is None:
        return None
    target_c, target_props = target
    output_names = sorted(name for name in target_props
                          if _mentioned(name, question))
    # A pluralized entity name must not become an accidental projection.
    output_names = [name for name in output_names
                    if name not in {label for label in target_c["target_labels"]}]
    if not output_names:
        return None
    # Only identifiers present as terminal properties on the same SHACL entity
    # can bridge two independent equalities.
    candidates = []
    for source_c, source_props in sources:
        if source_c["domain"] == target_domain:
            continue
        for bridge_c, bridge_props in prepared:
            if bridge_c["domain"] in (source_c["domain"], target_domain):
                continue
            left = _identifiers(source_props) & _identifiers(bridge_props)
            right = _identifiers(bridge_props) & _identifiers(target_props)
            for first in left:
                for second in right - {first}:
                    candidates.append((source_c, source_props, bridge_c,
                                       bridge_props, first, second))
    # A missing or ambiguous identifier route is not authorization to invent one.
    routes = {(s["domain"], b["domain"], a, z) for s, _, b, _, a, z in candidates}
    if not routes:
        return None
    if len(routes) != 1:
        raise ValueError("Ambiguous two-key identifier bridge")
    source_domain, bridge_domain, left_key, right_key = next(iter(routes))
    source = _choose([(s, p) for s, p, b, _, a, z in candidates
                      if (s["domain"], b["domain"], a, z) == next(iter(routes))],
                     "source entity")
    bridge = _choose([(b, p) for s, _, b, p, a, z in candidates
                      if (s["domain"], b["domain"], a, z) == next(iter(routes))],
                     "intermediate entity")
    if source is None or bridge is None:
        return None

    def side(candidate, props, keys):
        return {"domain": candidate["domain"], "root": candidate["root"],
                "end_shape": candidate["end"], "predicates": list(candidate["predicates"]),
                "evidence_ids": [e for h in candidate["_hops"] for e in h["evidence_ids"]],
                "keys": [{"label": name, "predicate": props[name]["predicate"],
                          "evidence_ids": list(props[name]["_hop"]["evidence_ids"])}
                         for name in keys]}
    s, sp = source
    b, bp = bridge
    return {"query_type": "SELECT", "intent": "list",
            "join_type": "shacl_multihop_identifier_join",
            "planner": "shacl_multihop_identifier_join",
            "join_keys": [left_key, right_key],
            "sides": [side(s, sp, [left_key]),
                      side(b, bp, [left_key, right_key]),
                      side(target_c, target_props, [right_key])],
            "projections": [{"label": name, "predicate": target_props[name]["predicate"],
                             "evidence_ids": list(target_props[name]["_hop"]["evidence_ids"])}
                            for name in output_names],
            "validation_scope": "SHACL paths verified; instance data not verified"}


def compile_multihop_projection(plan, schema, limit, graph_mode, graph_iri,
                                include_graph, count_per_graph, iri):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Result limit must be 1..1000")
    if (plan.get("join_type") != "shacl_multihop_identifier_join"
            or plan.get("intent") != "list" or count_per_graph
            or graph_mode not in ("default", "all_named") or graph_iri is not None
            or (include_graph and graph_mode != "all_named")):
        raise ValueError("Unsupported multihop query options")
    sides, keys, outputs = (plan.get("sides"), plan.get("join_keys"),
                            plan.get("projections"))
    if (not isinstance(sides, list) or len(sides) != 3
            or len({s.get("domain") for s in sides}) != 3
            or not isinstance(keys, list) or len(keys) != 2
            or len(set(keys)) != 2
            or not isinstance(outputs, list) or not 1 <= len(outputs) <= 12):
        raise ValueError("Invalid multihop topology")
    if [[k.get("label") for k in side.get("keys", [])] for side in sides] != [
            [keys[0]], keys, [keys[1]]]:
        raise ValueError("Invalid multihop join-key arrangement")
    blocks = []
    for i, side in enumerate(sides):
        predicates = side.get("predicates")
        root, end, domain = side.get("root"), side.get("end_shape"), side.get("domain")
        if not isinstance(predicates, list) or not predicates:
            raise ValueError("Empty multihop structural path")
        valid = any(hops and hops[-1].get("to_shape") == end
                    and [h["property"] for h in hops] == predicates
                    and [e for h in hops for e in h["evidence_ids"]] == side.get("evidence_ids")
                    and validate_hops(hops, schema, root)
                    for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain))
        if not valid:
            raise ValueError("Unverified multihop structural path")

        def terminal(prop):
            pred, evidence = prop.get("predicate"), prop.get("evidence_ids")
            return (schema.by_uri.get(pred, {}).get("domain") == domain
                    and any(len(hops) == 1 and hops[0].get("to_shape") is None
                            and hops[0]["property"] == pred
                            and hops[0]["evidence_ids"] == evidence
                            and validate_hops(hops, schema, end)
                            for hops in schema.shacl_paths(end, max_depth=1, domain=domain)))
        vars_ = [f"?root{i}"] + [f"?node{i}_{j}" for j in range(1, len(predicates))] + [f"?entity{i}"]
        triples = [f"{vars_[j]} {iri(p)} {vars_[j+1]} ."
                   for j, p in enumerate(predicates)]
        for key in side["keys"]:
            if (key.get("label") not in keys or not terminal(key)
                    or key["label"] not in schema.by_uri[key["predicate"]].get("labels", [])):
                raise ValueError("Unverified multihop identifier")
            triples.append(f"?entity{i} {iri(key['predicate'])} ?joinKey{keys.index(key['label'])} .")
        if i == 2:
            for j, output in enumerate(outputs):
                if (not terminal(output)
                        or output.get("label") not in schema.by_uri[output["predicate"]].get("labels", [])):
                    raise ValueError("Unverified multihop projection")
                pattern = f"?entity{i} {iri(output['predicate'])} ?value{j} ."
                if output["label"] in keys:
                    triples.append(pattern)
                else:
                    triples.append(f"OPTIONAL {{ {pattern} }}")
        body = "\n".join("    " + t for t in triples)
        blocks.append(f"  GRAPH ?graph{i} {{\n{body}\n  }}" if graph_mode == "all_named"
                      else body)
    projected = [f"?value{j}" for j in range(len(outputs))]
    if include_graph:
        projected += [f"?graph{i}" for i in range(3)]
    return ("SELECT DISTINCT " + " ".join(projected)
            + "\nWHERE {\n" + "\n".join(blocks)
            + "\n}\nORDER BY " + " ".join(f"?value{j}" for j in range(len(outputs)))
            + f"\nLIMIT {limit}")
