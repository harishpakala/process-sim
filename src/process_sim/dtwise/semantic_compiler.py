"""SPARQL compiler for validated compositional semantic IR 2.0.

Initial supported subset: one selected SHACL entity shape. Multiple entity
joins require an explicit relationship binding stage and fail closed here.
"""
from __future__ import annotations

import json

from .semantic_planning import validate_semantic_plan
from .unified_ir import _iri, _literal


def compile_semantic_plan(plan, evidence, *, graph_mode="all_named",
                          graph_iri=None, limit=None):
    """Compile verified evidence IDs into named-graph-aware SPARQL."""
    plan = validate_semantic_plan(plan, evidence)
    if len(plan["scope"]) > 1 and plan.get("scope_mode") == "independent":
        if plan["operation"] == "select_values":
            raise ValueError("Independent multi-shape value projections are not yet supported")
        props = {p["id"]: p for p in evidence.properties}
        entities = {e["id"]: e for e in evidence.entities}
        used = set()
        def visit(node):
            if node is None:
                return
            if node["operator"] in ("and", "or"):
                for child in node["conditions"]:
                    visit(child)
            elif node["operator"] == "not":
                visit(node["condition"])
            else:
                used.add(node["property_id"])
        visit(plan["where"])
        owners = {props[p]["entity_id"] for p in used}
        if len(owners) > 1:
            raise ValueError("Independent scope cannot combine properties owned by distinct shapes")
        # An independent branch must have explicit type membership evidence.
        # A shape without a target class cannot safely contribute to a
        # domain-wide union, even if its properties overlap another shape.
        for entity_id in plan["scope"]:
            if not entities[entity_id].get("target_classes"):
                raise ValueError("Independent scope requires verified targetClass for every shape")
        branches = []
        for entity_id in plan["scope"]:
            if owners and entity_id not in owners:
                continue
            subplan = dict(plan, scope=[entity_id], scope_mode="single",
                           operation="select_entities")
            branch = compile_semantic_plan(subplan, evidence,
                graph_mode=graph_mode, graph_iri=graph_iri, limit=None)
            # Subquery returns ?entity; UNION branches never imply joins.
            branches.append("{ " + branch + " }")
        if not branches:
            raise ValueError("No eligible independent entity branches")
        if plan["operation"] == "count":
            query = "SELECT (COUNT(DISTINCT ?entity) AS ?count) WHERE { " + (
                " UNION ".join(branches)) + " }"
        else:
            query = "SELECT DISTINCT ?entity WHERE { " + (
                " UNION ".join(branches)) + " }"
        if limit is not None:
            if type(limit) is not int or not 1 <= limit <= 10000:
                raise ValueError("Invalid operational limit")
            query += "\nLIMIT " + str(limit)
        return query
    if len(plan["scope"]) != 1:
        owners = {p["id"]: p["entity_id"] for p in evidence.properties}
        selected = set(plan["scope"])
        used = set(plan["projections"])
        def collect(node):
            if node is None:
                return
            if node["operator"] in ("and", "or"):
                for child in node["conditions"]:
                    collect(child)
            elif node["operator"] == "not":
                collect(node["condition"])
            else:
                used.add(node["property_id"])
        collect(plan["where"])
        involved = sorted({owners[p] for p in used})
        if len(involved) > 1:
            raise ValueError(
                "Multi-shape plan references properties owned by distinct shapes "
                + repr(involved) + "; no explicit join or independent-branch "
                "semantics are encoded. Refusing to infer either.")
        raise ValueError(
            "Multi-shape scope " + repr(sorted(selected)) +
            " lacks verified shape membership and explicit independent-branch "
            "semantics; refusing to infer joins or union results.")
    if graph_mode not in ("default", "all_named", "selected"):
        raise ValueError("Unsupported graph mode")
    if graph_mode == "selected":
        graph = _iri(graph_iri)
    elif graph_iri is not None:
        raise ValueError("graph_iri requires selected graph mode")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 10000):
        raise ValueError("Invalid operational limit")
    properties = {p["id"]: p for p in evidence.properties}
    entity_id = plan["scope"][0]

    def scoped(body, suffix):
        if graph_mode == "default":
            return body
        name = graph if graph_mode == "selected" else "?g_" + suffix
        return "GRAPH " + name + " { " + body + " }"

    counter = [0]

    def fresh():
        counter[0] += 1
        return str(counter[0])

    def leaf(node):
        prop = properties[node["property_id"]]
        if prop["entity_id"] != entity_id:
            raise ValueError("Property ownership mismatch")
        suffix = fresh()
        value_var = "?v_" + suffix
        triple = "?entity " + _iri(prop["predicate"]) + " " + value_var + " ."
        triple = scoped(triple, suffix)
        op = node["operator"]
        if op == "exists":
            return "EXISTS { " + triple + " }"
        if op == "not_exists":
            return "NOT EXISTS { " + triple + " }"
        value = node["value"]
        if op == "regex":
            condition = "REGEX(STR(" + value_var + "), " + json.dumps(
                str(value), ensure_ascii=True) + ")"
        elif op == "contains":
            condition = "CONTAINS(LCASE(STR(" + value_var + ")), LCASE(STR(" + _literal(value) + ")))"
        else:
            condition = value_var + (" = " if op == "eq" else " != ") + _literal(value)
        return "EXISTS { " + triple + " FILTER(" + condition + ") }"

    def expression(node):
        op = node["operator"]
        if op in ("and", "or"):
            joiner = " && " if op == "and" else " || "
            return "(" + joiner.join(
                "(" + expression(child) + ")" for child in node["conditions"]) + ")"
        if op == "not":
            return "!(" + expression(node["condition"]) + ")"
        return leaf(node)

    # A property-presence pattern establishes the entity binding without
    # inferring rdf:type from a SHACL node shape. This is a broad SHACL-backed
    # candidate universe, not a type assertion.
    selected_entity = next(e for e in evidence.entities if e["id"] == entity_id)
    target_classes = selected_entity.get("target_classes", [])
    eligible = sorted((p for p in evidence.properties
                       if p["entity_id"] == entity_id), key=lambda p: p["id"])
    anchors = []
    if target_classes:
        # A SHACL sh:targetClass is explicit rdf:type membership evidence.
        # Never infer type membership merely from a property predicate.
        for target_class in target_classes:
            suffix = fresh()
            anchors.append("{ " + scoped(
                "?entity <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
                + _iri(target_class) + " .", suffix) + " }")
    else:
        if not eligible:
            raise ValueError("Selected entity has no SHACL property evidence")
        for prop in eligible:
            suffix = fresh()
            anchors.append("{ " + scoped(
                "?entity " + _iri(prop["predicate"]) + " ?anchor_" + suffix + " .",
                suffix) + " }")
    body = ["{ " + " UNION ".join(anchors) + " }"]
    if plan["where"] is not None:
        body.append("FILTER(" + expression(plan["where"]) + ")")
    if plan["operation"] == "select_values":
        for index, prop_id in enumerate(plan["projections"]):
            prop = properties[prop_id]
            suffix = fresh()
            body.append(scoped(
                "?entity " + _iri(prop["predicate"]) + " ?value_" + str(index) + " .",
                suffix))
        columns = "?entity " + " ".join(
            "?value_" + str(i) for i in range(len(plan["projections"])))
        head = "SELECT DISTINCT " + columns
    elif plan["operation"] == "count":
        head = "SELECT (COUNT(DISTINCT ?entity) AS ?count)"
    else:
        head = "SELECT DISTINCT ?entity"
    query = head + "\nWHERE {\n  " + "\n  ".join(body) + "\n}"
    if limit is not None:
        query += "\nLIMIT " + str(limit)
    return query
