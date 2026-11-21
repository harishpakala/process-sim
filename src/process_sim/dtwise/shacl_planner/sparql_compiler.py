"""Deterministic, fail-closed SPARQL SELECT compiler for validated single-domain plans.

No LLM calls. Only predicates and class constraints present in the SHACL index
are emitted. This module does not execute queries or assert data-store compatibility.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SH_CLASS = "http://www.w3.org/ns/shacl#class"
SH_TARGET_CLASS = "http://www.w3.org/ns/shacl#targetClass"
OPERATORS = {"=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


class CompilationError(ValueError):
    """Plan cannot be compiled without inventing RDF semantics."""


def _iri(value):
    if not isinstance(value, str) or not re.fullmatch(r"https?://[^\s<>\x00-\x20]+", value):
        raise CompilationError("Invalid or unsupported RDF IRI")
    return "<" + value + ">"


def _literal(value):
    if not isinstance(value, str):
        raise CompilationError("Filter value must be a string")
    return json.dumps(value, ensure_ascii=False)


def _class_map(schema, domain):
    result = defaultdict(set)
    for rel in schema.get("relationships", []):
        if rel.get("domain") == domain and rel.get("predicate") in (SH_CLASS, SH_TARGET_CLASS):
            result[rel["subject"]].add(rel["object"])
    return result


def compile_single_domain(record, index, schema):
    """Compile one valid run_one record using the same domain's verified index.

    Returns SPARQL SELECT text. Rejects missing/ambiguous class grounding,
    unsupported COUNT, nontrivial branch joins, and unverifiable candidate IDs.
    """
    if record.get("status") != "valid_response" or record.get("validation_errors"):
        raise CompilationError("Only validated Phase-1 plans can be compiled")
    answer = record.get("answer") or {}
    if answer.get("status") != "selected":
        raise CompilationError("No selected plan")
    if answer.get("count_target_id") is not None:
        raise CompilationError("COUNT compilation not implemented")
    if answer.get("join") or answer.get("join_owner_id") is not None:
        raise CompilationError("Branch joins are not supported by this compiler")
    domain = index.domain
    if record.get("domain") not in (None, domain):
        raise CompilationError("Domain mismatch")
    registry = record.get("candidate_registry") or {}
    offered = {c["id"]: c for c in record.get("candidate_paths", [])}
    class_map = _class_map(schema, domain)
    valid_edges = {(e["from"], e["predicate"], e["to"], e["property_shape"])
                   for e in index.edges}
    valid_props = {(p["owner"], p["predicate"], p["property_shape"])
                   for props in index.properties.values() for p in props}
    selected = list(answer.get("projection_ids") or []) + list(answer.get("existence_ids") or [])
    selected += [f["property_id"] for f in answer.get("filters") or []]
    selected += [o["property_id"] for o in answer.get("order_by") or []]
    if not selected or len(set(answer.get("projection_ids") or [])) != len(answer.get("projection_ids") or []):
        raise CompilationError("Missing or duplicate projections")

    # Validate the full selected candidate topology independently of the model.
    for cid in selected:
        entry = registry.get(cid)
        offered_entry = offered.get(cid)
        if not entry or not offered_entry or entry.get("kind") != offered_entry.get("kind"):
            raise CompilationError("Unknown candidate ID: " + str(cid))
        if entry.get("domain") != domain:
            raise CompilationError("Cross-domain candidate in single-domain plan")
        nodes, edges = entry.get("node_uris") or [], entry.get("edges") or []
        if not nodes or len(edges) != len(nodes) - 1 or any(n not in index.shapes for n in nodes):
            raise CompilationError("Unverified shape sequence")
        for i, edge in enumerate(edges):
            signature = (edge["from"], edge["predicate"], edge["to"], edge["property_shape"])
            if signature not in valid_edges or edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
                raise CompilationError("Unverified traversal edge")
        if entry["kind"] == "property":
            prop = entry.get("property") or {}
            signature = (prop.get("owner"), prop.get("predicate"), prop.get("property_shape"))
            if signature not in valid_props or prop["owner"] != nodes[-1]:
                raise CompilationError("Unverified property predicate")

    # A selected path is rooted at a SHACL shape; class identity is taken from
    # explicit SHACL class/targetClass constraints, never guessed from shape names.
    roots = {registry[cid]["node_uris"][0] for cid in selected}
    if len(roots) != 1:
        raise CompilationError("Multiple independent roots require explicit join semantics")
    root = next(iter(roots))
    classes = class_map.get(root, set())
    if len(classes) != 1:
        raise CompilationError("Root shape lacks one unambiguous SHACL class")
    root_triple = f"?n0 {_iri(RDF_TYPE)} {_iri(next(iter(classes)))} ."
    # Allocate variables by verified path prefix, not by depth: sibling
    # branches must never be conflated just because they have equal depth.
    prefix_vars = {(root,): "?n0"}
    for cid in selected:
        nodes = registry[cid]["node_uris"]
        for depth in range(2, len(nodes) + 1):
            prefix = tuple(nodes[:depth])
            if prefix not in prefix_vars:
                prefix_vars[prefix] = f"?n{len(prefix_vars)}"

    def path_triples(cid):
        entry = registry[cid]
        nodes = entry["node_uris"]
        triples = set()
        for depth, edge in enumerate(entry["edges"], 1):
            parent = prefix_vars[tuple(nodes[:depth])]
            child = prefix_vars[tuple(nodes[:depth + 1])]
            triples.add(f"{parent} {_iri(edge['predicate'])} {child} .")
        if entry["kind"] == "property":
            variable = variables[cid]
            owner = prefix_vars[tuple(nodes)]
            triples.add(f"{owner} {_iri(entry['property']['predicate'])} {variable} .")
        return triples

    variables = {}
    for cid in selected:
        entry = registry[cid]
        if entry["kind"] == "result":
            variables[cid] = prefix_vars[tuple(entry["node_uris"])]
        else:
            variables[cid] = "?v_" + re.sub(r"[^A-Za-z0-9_]", "_", cid)

    filters = answer.get("filters") or []
    boolean = answer.get("boolean_operator")
    if filters and boolean not in ("NONE", "AND", "OR"):
        raise CompilationError("Invalid boolean operator")
    if len(filters) > 1 and boolean == "NONE":
        raise CompilationError("Multiple filters without a boolean operator")

    conditions = []
    for f in filters:
        op = OPERATORS.get(f.get("operator"))
        if not op:
            raise CompilationError("Unsupported comparison operator")
        conditions.append("(" + variables[f["property_id"]] + " " + op +
                          " " + _literal(f["value"]) + ")")

    # Projection, existence and sorting paths remain mandatory. OR filter
    # branches are UNION alternatives, each containing its own full verified
    # traversal and value constraint. This handles nested paths and repeated
    # values on the same property without requiring either branch to exist.
    mandatory_ids = list(answer.get("projection_ids") or [])
    mandatory_ids += list(answer.get("existence_ids") or [])
    mandatory_ids += [o["property_id"] for o in answer.get("order_by") or []]
    is_or = boolean == "OR" and len(filters) > 1
    if not is_or:
        mandatory_ids += [f["property_id"] for f in filters]
    triples = {root_triple}
    for cid in mandatory_ids:
        triples.update(path_triples(cid))
    lines = sorted(triples)
    if is_or:
        branches = []
        for f, condition in zip(filters, conditions):
            branch_lines = sorted(path_triples(f["property_id"]))
            branch_lines.append("FILTER (" + condition + ")")
            branches.append("{ " + " ".join(branch_lines) + " }")
        lines.append(" UNION ".join(branches))
    elif conditions:
        lines.append("FILTER (" + " && ".join(conditions) + ")")
    projections = answer.get("projection_ids") or []
    if not projections:
        raise CompilationError("SELECT requires projections")
    projected_vars = list(dict.fromkeys(variables[cid] for cid in projections))
    query = "SELECT " + " ".join(projected_vars) + " WHERE {\n  "
    query += "\n  ".join(lines) + "\n}"
    orders = answer.get("order_by") or []
    if orders:
        clauses = []
        for order in orders:
            if order.get("direction") not in ("ASC", "DESC"):
                raise CompilationError("Invalid sort direction")
            clauses.append(order["direction"] + "(" + variables[order["property_id"]] + ")")
        query += "\nORDER BY " + " ".join(clauses)
    limit = answer.get("limit")
    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise CompilationError("Invalid LIMIT")
        query += "\nLIMIT " + str(limit)
    return query + "\n"
