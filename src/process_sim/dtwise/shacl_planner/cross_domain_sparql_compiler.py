"""Fail-closed graph-scoped SELECT compiler for validated cross-domain Phase-1 plans."""
import json
import re
from collections import defaultdict

from process_sim.dtwise.shacl_planner.sparql_compiler import (
    CompilationError, _iri, _literal, _class_map, OPERATORS, RDF_TYPE,
)


def compile_cross_domain(record, indices, schema, graphs, approved_mappings):
    if record.get("status") != "valid_response" or record.get("validation_errors"):
        raise CompilationError("Cross-domain plan is not validated")
    answer = record.get("answer") or {}
    if answer.get("status") != "selected":
        raise CompilationError("No selected plan")
    if answer.get("count_target_id") is not None:
        raise CompilationError("Cross-domain COUNT not yet supported")
    if answer.get("join_owner_id") is not None:
        raise CompilationError("Unsupported branch join")
    domains = set(record.get("domains") or [])
    if domains != set(indices) or not domains.issubset(graphs):
        raise CompilationError("Domain or named-graph mismatch")
    offered = {c["id"]: c for c in record.get("candidate_paths") or []}
    identifiers = {c["id"]: c for c in record.get("identifier_path_candidates") or []}
    mappings = {m["id"]: m for m in record.get("mapping_candidates") or []}
    approved = {m["id"]: m for m in approved_mappings if m.get("verified") is True}
    selected_mappings = answer.get("mapping_ids") or []
    selected_identifiers = set(answer.get("identifier_path_ids") or [])
    if not selected_mappings or not selected_identifiers or len(selected_mappings) != len(set(selected_mappings)):
        raise CompilationError("Missing or duplicate approved mapping selection")
    selected = list(answer.get("projection_ids") or []) + list(answer.get("existence_ids") or [])
    selected += [f["property_id"] for f in answer.get("filters") or []]
    selected += [o["property_id"] for o in answer.get("order_by") or []]
    selected += sorted(selected_identifiers)
    if not answer.get("projection_ids"):
        raise CompilationError("Missing projections")
    for cid in selected:
        if cid not in offered:
            raise CompilationError("Unrecognized candidate " + cid)
    graph_lines = defaultdict(set)
    variables = {}
    roots = {}
    prefixes = {}
    next_variable = 0
    for cid in dict.fromkeys(selected):
        c = offered[cid]
        domain = c.get("domain")
        if domain not in domains or not cid.startswith(domain + ":"):
            raise CompilationError("Candidate domain mismatch")
        index = indices[domain]
        nodes = c.get("node_uris") or []
        if not nodes or any(n not in index.shapes for n in nodes):
            raise CompilationError("Unverified candidate shape path")
        root = nodes[0]
        classes = _class_map(schema, domain).get(root, set())
        if len(classes) != 1:
            raise CompilationError("Root shape class is ambiguous")
        root_key = (domain, root)
        if root_key not in roots:
            roots[root_key] = "?n" + str(next_variable)
            next_variable += 1
        root_var = roots[root_key]
        graph_lines[domain].add(f"{root_var} {_iri(RDF_TYPE)} {_iri(next(iter(classes)))} .")
        prefix = (domain, root)
        prefixes[prefix] = root_var
        for i in range(1, len(nodes)):
            parent = nodes[i - 1]
            child = nodes[i]
            edges = [e for e in index.edges if e["from"] == parent and e["to"] == child]
            predicates = {e["predicate"] for e in edges}
            if len(predicates) != 1:
                raise CompilationError("Ambiguous SHACL traversal")
            child_key = (domain, *nodes[:i + 1])
            if child_key not in prefixes:
                prefixes[child_key] = "?n" + str(next_variable)
                next_variable += 1
            graph_lines[domain].add(f"{prefixes[(domain, *nodes[:i])]} {_iri(next(iter(predicates)))} {prefixes[child_key]} .")
        owner_var = prefixes[(domain, *nodes)]
        if c.get("kind") == "result":
            variables[cid] = owner_var
        elif c.get("kind") == "property":
            props = [p for p in index.properties.get(nodes[-1], [])
                     if p.get("owner") == nodes[-1]]
            label = c.get("path", "").split(" → ")[-1].casefold()
            matching = {p["predicate"] for p in props
                        if p.get("name", "").casefold() == label or
                        p.get("label", "").casefold() == label or
                        p["predicate"].rsplit("/", 1)[-1].rsplit("#", 1)[-1].casefold() == label}
            if cid in identifiers:
                matching = {identifiers[cid]["predicate"]} & {p["predicate"] for p in props}
            if len(matching) != 1:
                raise CompilationError("Ambiguous property grounding for " + cid)
            variables[cid] = "?v_" + re.sub(r"[^A-Za-z0-9_]", "_", cid)
            graph_lines[domain].add(f"{owner_var} {_iri(next(iter(matching)))} {variables[cid]} .")
        else:
            raise CompilationError("Unsupported candidate kind")
    used_identifiers = set()
    for mid in selected_mappings:
        mapping = mappings.get(mid)
        source = approved.get(mid)
        if not mapping or not source or any(mapping.get(k) != source.get(k) for k in
                ("left_domain", "right_domain", "left_property", "right_property")):
            raise CompilationError("Mapping is not independently approved")
        left = selected_identifiers.intersection(mapping["left_identifier_candidate_ids"])
        right = selected_identifiers.intersection(mapping["right_identifier_candidate_ids"])
        allowed = {(p["left_id"], p["right_id"]) for p in mapping.get("join_alternatives") or []}
        if len(left) != 1 or len(right) != 1 or (next(iter(left)), next(iter(right))) not in allowed:
            raise CompilationError("Mapping endpoints are ambiguous or unapproved")
        a, b = next(iter(left)), next(iter(right))
        if identifiers[a]["predicate"] != source["left_property"] or identifiers[b]["predicate"] != source["right_property"]:
            raise CompilationError("Mapping predicate mismatch")
        used_identifiers.update((a, b))
        graph_lines["_filters"].add(f"FILTER ({variables[a]} = {variables[b]})")
    if used_identifiers != selected_identifiers:
        raise CompilationError("Dangling identifier path")
    conditions = []
    for f in answer.get("filters") or []:
        op = OPERATORS.get(f.get("operator"))
        if not op:
            raise CompilationError("Unsupported filter operator")
        conditions.append(f"({variables[f['property_id']]} {op} {_literal(f['value'])})")
    boolean = answer.get("boolean_operator")
    if len(conditions) > 1 and boolean not in ("AND", "OR"):
        raise CompilationError("Unsupported filter boolean")
    if conditions:
        graph_lines["_filters"].add("FILTER (" + (" || " if boolean == "OR" else " && ").join(conditions) + ")")
    projections = list(dict.fromkeys(variables[cid] for cid in answer["projection_ids"]))
    lines = []
    for domain in sorted(domains):
        lines.append(f"  GRAPH {_iri(graphs[domain])} {{")
        lines.extend("    " + line for line in sorted(graph_lines[domain]))
        lines.append("  }")
    lines.extend("  " + line for line in sorted(graph_lines["_filters"]))
    query = "SELECT DISTINCT " + " ".join(projections) + " WHERE {\n" + "\n".join(lines) + "\n}"
    orders = answer.get("order_by") or []
    if orders:
        clauses = []
        for o in orders:
            if o.get("direction") not in ("ASC", "DESC"):
                raise CompilationError("Unsupported order direction")
            clauses.append(o["direction"] + "(" + variables[o["property_id"]] + ")")
        query += "\nORDER BY " + " ".join(clauses)
    limit = answer.get("limit")
    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise CompilationError("Invalid LIMIT")
        query += "\nLIMIT " + str(limit)
    return query + "\n"
