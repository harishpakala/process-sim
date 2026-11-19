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
    if len(plan["scope"]) != 1:
        raise ValueError("Multi-entity semantic compilation requires explicit joins")
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
            return "FILTER EXISTS { " + triple + " }"
        if op == "not_exists":
            return "FILTER NOT EXISTS { " + triple + " }"
        value = node["value"]
        if op == "regex":
            condition = "REGEX(STR(" + value_var + "), " + json.dumps(
                str(value), ensure_ascii=True) + ")"
        elif op == "contains":
            condition = "CONTAINS(LCASE(STR(" + value_var + ")), LCASE(STR(" + _literal(value) + ")))"
        else:
            condition = value_var + (" = " if op == "eq" else " != ") + _literal(value)
        return "FILTER EXISTS { " + triple + " FILTER(" + condition + ") }"

    def expression(node):
        op = node["operator"]
        if op == "and":
            return "\n".join(expression(child) for child in node["conditions"])
        if op == "or":
            return "{ " + " UNION ".join(
                "{ " + expression(child) + " }" for child in node["conditions"]) + " }"
        if op == "not":
            # NOT EXISTS wraps a correlated subquery, preserving arbitrary
            # nested Boolean expressions and the outer ?entity binding.
            return "FILTER NOT EXISTS { " + expression(node["condition"]) + " }"
        return leaf(node)

    # A property-presence pattern establishes the entity binding without
    # inferring rdf:type from a SHACL node shape. This is a broad SHACL-backed
    # candidate universe, not a type assertion.
    eligible = sorted((p for p in evidence.properties
                       if p["entity_id"] == entity_id), key=lambda p: p["id"])
    if not eligible:
        raise ValueError("Selected entity has no SHACL property evidence")
    anchors = []
    for prop in eligible:
        suffix = fresh()
        anchors.append("{ " + scoped(
            "?entity " + _iri(prop["predicate"]) + " ?anchor_" + suffix + " .",
            suffix) + " }")
    body = ["{ " + " UNION ".join(anchors) + " }"]
    if plan["where"] is not None:
        body.append(expression(plan["where"]))
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
