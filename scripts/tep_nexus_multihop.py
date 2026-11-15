"""Independent, fail-closed SHACL-backed multi-hop join planner.

Does not import or modify the frozen DTwise package. This first version
supports explicit three-domain, same-identifier joins; it is not wired into
the HTTP adapter until GraphDB and regression tests validate its behavior.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SH_PROPERTY = "http://www.w3.org/ns/shacl#property"
SH_TARGET_CLASS = "http://www.w3.org/ns/shacl#targetClass"

class MultiHopRejected(ValueError):
    """Question or schema does not establish an unambiguous multi-hop path."""


def _mentions(text: str, label: str) -> bool:
    words = re.findall(r"[a-z0-9]+", label.casefold())
    return bool(words) and bool(re.search(
        r"(?<![a-z0-9])" + r"\s*".join(map(re.escape, words)) + r"(?![a-z0-9])",
        text.casefold(),
    ))


def _entity(data, domain, label):
    classes = [c for c in data["concepts"]
               if c.get("domain") == domain and c.get("kind") == "class"
               and label in c.get("labels", [])]
    if len(classes) != 1:
        raise MultiHopRejected(f"Expected one class for {domain}.{label}")
    relationships = data["relationships"]
    shapes = [r["subject"] for r in relationships
              if r.get("domain") == domain and r.get("predicate") == SH_TARGET_CLASS
              and r.get("object") == classes[0]["uri"]]
    if len(set(shapes)) != 1:
        raise MultiHopRejected(f"Ambiguous target shape for {domain}.{label}")
    return classes[0]["uri"], shapes[0]


def _identifier_path(data, domain, node_shape):
    links = {r["object"] for r in data["relationships"]
             if r.get("domain") == domain and r.get("predicate") == SH_PROPERTY
             and r.get("subject") == node_shape}
    paths = {p["path"] for p in data["shape_paths"]
             if p.get("domain") == domain and p.get("node_shape") == node_shape
             and p.get("property_shape") in links
             and p.get("path", "").rsplit("/", 1)[-1] == "hasAssetIdentifier"}
    if len(paths) != 1:
        raise MultiHopRejected(f"Missing/ambiguous AssetIdentifier path: {domain}")
    return paths.pop()


def plan(question: str, schema_path):
    """Resolve a three-domain path using class and SHACL property evidence.

    Unsupported requests are rejected; no guessing or generic fallback.
    """
    if not isinstance(question, str):
        raise MultiHopRejected("Question must be text")
    if not (_mentions(question, "DEXPI")
            and (_mentions(question, "OPCUA") or _mentions(question, "OPCUAConnectivity"))
            and _mentions(question, "AssetInventory")
            and re.search(r"\b(?:via|through)\s+AssetInventory\b", question, re.I)
            and _mentions(question, "InstrumentationFunctions")
            and _mentions(question, "SignalMappings")):
        raise MultiHopRejected("Requires explicit DEXPI InstrumentationFunctions, OPCUA SignalMappings through AssetInventory")
    data = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    specs = (
        ("dexpi", "InstrumentationFunction"),
        ("assetinventory", "Asset"),
        ("opcuaconnectivity", "SignalMapping"),
    )
    entities = []
    for domain, label in specs:
        class_uri, node_shape = _entity(data, domain, label)
        predicate = _identifier_path(data, domain, node_shape)
        entities.append({"domain": domain, "class": class_uri,
                         "node_shape": node_shape, "identifier_predicate": predicate})
    return {"kind": "shacl_multihop_same_identifier", "entities": entities,
            "join_edges": [[0, 1], [1, 2]], "join_property": "AssetIdentifier"}


def compile_sparql(plan_data, *, limit=100):
    if not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("Limit must be between 1 and 5000")
    if plan_data.get("kind") != "shacl_multihop_same_identifier":
        raise MultiHopRejected("Unsupported multi-hop plan")
    entities = plan_data["entities"]
    if len(entities) != 3 or plan_data.get("join_edges") != [[0, 1], [1, 2]]:
        raise MultiHopRejected("Unexpected join structure")
    for e in entities:
        if not all(isinstance(e.get(k), str) and e[k].startswith(("http://", "https://"))
                   and ">" not in e[k] and "<" not in e[k]
                   for k in ("class", "identifier_predicate")):
            raise MultiHopRejected("Invalid schema URI")
    variables = ("?function", "?inventoryAsset", "?mapping")
    lines = ["SELECT DISTINCT ?function ?assetIdentifier ?inventoryAsset ?mapping",
             "WHERE {"]
    for variable, entity in zip(variables, entities):
        lines.append(f"  {variable} a <{entity['class']}> .")
        lines.append(f"  {variable} <{entity['identifier_predicate']}> ?assetIdentifier .")
    lines.extend(["}", "ORDER BY ?assetIdentifier", f"LIMIT {limit}"])
    return "\n".join(lines)
