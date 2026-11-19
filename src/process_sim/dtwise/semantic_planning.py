"""Composable evidence-grounded semantic planning primitives.

This module deliberately does not parse natural language or compile SPARQL.
The LLM selects opaque evidence IDs; validation resolves only SHACL-backed
owners and recursively validates Boolean expressions. No benchmark templates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceCatalog:
    entities: tuple[dict, ...]
    properties: tuple[dict, ...]
    relationships: tuple[dict, ...]

    def as_prompt(self) -> dict:
        return {
            "entities": list(self.entities),
            "properties": list(self.properties),
            "relationships": list(self.relationships),
        }


def build_evidence_catalog(catalog: dict) -> EvidenceCatalog:
    """Assign stable opaque IDs to verified shape/property ownership and edges."""
    owners = sorted({
        (entity["domain"], entity["shape"], predicate)
        for entity in catalog["entities"]
        for predicate in entity["properties"]
    })
    shapes = sorted({
        (entity["domain"], entity["shape"])
        for entity in catalog["entities"]
    })
    shape_ids = {key: f"S{i}" for i, key in enumerate(shapes)}
    entities = tuple({
        "id": shape_ids[key], "domain": key[0], "shape": key[1]
    } for key in shapes)
    properties = tuple({
        "id": f"P{i}", "entity_id": shape_ids[(domain, shape)],
        "predicate": predicate,
        "label": predicate.rsplit("/", 1)[-1].rsplit("#", 1)[-1],
    } for i, (domain, shape, predicate) in enumerate(owners))
    edges = sorted({
        (edge["domain"], edge["from_shape"], edge["predicate"], edge["to_shape"])
        for edge in catalog.get("shacl_edges", [])
        if (edge["domain"], edge["from_shape"]) in shape_ids
        and (edge["domain"], edge["to_shape"]) in shape_ids
    })
    relationships = tuple({
        "id": f"R{i}", "from_entity_id": shape_ids[(domain, source)],
        "to_entity_id": shape_ids[(domain, target)], "predicate": predicate,
    } for i, (domain, source, predicate, target) in enumerate(edges))
    return EvidenceCatalog(entities, properties, relationships)


def validate_semantic_plan(plan: dict, evidence: EvidenceCatalog) -> dict:
    """Fail closed on unsupported expressions, invented IDs and wrong ownership.

    Returns a normalized plan with original evidence IDs; the compiler can
    resolve them using the independently constructed evidence catalog.
    """
    if not isinstance(plan, dict) or set(plan) != {
        "version", "scope", "operation", "projections", "where"
    } or plan["version"] != "2.0":
        raise ValueError("Invalid semantic plan structure")
    entities = {x["id"]: x for x in evidence.entities}
    properties = {x["id"]: x for x in evidence.properties}
    scope = plan["scope"]
    if not isinstance(scope, list) or not scope or len(scope) > 32:
        raise ValueError("Invalid entity scope")
    if any(not isinstance(s, str) or s not in entities for s in scope):
        raise ValueError("Invented entity evidence ID")
    if len(set(scope)) != len(scope):
        raise ValueError("Duplicate entity evidence ID")
    if plan["operation"] not in ("select_entities", "select_values", "count"):
        raise ValueError("Unsupported semantic operation")
    projections = plan["projections"]
    if not isinstance(projections, list) or len(projections) > 64:
        raise ValueError("Invalid projections")
    if any(not isinstance(p, str) or p not in properties for p in projections):
        raise ValueError("Invented projection evidence ID")
    if any(properties[p]["entity_id"] not in scope for p in projections):
        raise ValueError("Projection property outside selected scope")
    if plan["operation"] == "select_values" and not projections:
        raise ValueError("Value selection requires projections")
    if plan["operation"] != "select_values" and projections:
        raise ValueError("Entity/count selection cannot project property values")

    def expression(node: Any, depth: int = 0) -> dict:
        if depth > 16 or not isinstance(node, dict):
            raise ValueError("Invalid Boolean expression")
        op = node.get("operator")
        if op in ("and", "or"):
            if set(node) != {"operator", "conditions"}:
                raise ValueError("Invalid Boolean connective structure")
            children = node["conditions"]
            if not isinstance(children, list) or not 2 <= len(children) <= 64:
                raise ValueError("Boolean connective needs 2-64 conditions")
            return {"operator": op, "conditions": [
                expression(child, depth + 1) for child in children
            ]}
        if op == "not":
            if set(node) != {"operator", "condition"}:
                raise ValueError("Invalid negation structure")
            return {"operator": op, "condition": expression(node["condition"], depth + 1)}
        if op in ("exists", "not_exists"):
            if set(node) != {"operator", "property_id"}:
                raise ValueError("Invalid property presence condition")
            prop = node["property_id"]
            if not isinstance(prop, str) or prop not in properties:
                raise ValueError("Invented property evidence ID")
            if properties[prop]["entity_id"] not in scope:
                raise ValueError("Filter property outside selected scope")
            return {"operator": op, "property_id": prop}
        if op in ("eq", "neq", "contains", "regex"):
            if set(node) != {"operator", "property_id", "value"}:
                raise ValueError("Invalid comparison structure")
            prop, value = node["property_id"], node["value"]
            if not isinstance(prop, str) or prop not in properties:
                raise ValueError("Invented property evidence ID")
            if properties[prop]["entity_id"] not in scope:
                raise ValueError("Filter property outside selected scope")
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                raise ValueError("Comparison requires a scalar literal")
            return {"operator": op, "property_id": prop, "value": value}
        raise ValueError("Unsupported Boolean operation")

    where = plan["where"]
    normalized_where = None if where is None else expression(where)
    return {
        "version": "2.0", "scope": list(scope),
        "operation": plan["operation"], "projections": list(projections),
        "where": normalized_where,
    }
