#!/usr/bin/env python3
"""Select catalog-supported typed relationship paths, rejecting unsupported semantics."""
import json
from collections import deque
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "semantic/ontology/dtwise_relationship_catalog.json"

def load_catalog(path=CATALOG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [edge["id"] for edge in data["edges"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate relationship IDs")
    for edge in data["edges"]:
        if edge["from"] not in data["nodes"] or edge["to"] not in data["nodes"]:
            raise ValueError("Unknown edge endpoint type")
        if edge["direction"] not in {"forward", "reverse"}:
            raise ValueError("Unknown edge direction")
    return data

def select_path(catalog, intent_name):
    intent = catalog["intents"].get(intent_name)
    if not intent:
        raise ValueError("UNSUPPORTED_INTENT: " + intent_name)
    permitted = set(intent["allowed_edges"])
    edges = [e for e in catalog["edges"] if e["id"] in permitted]
    if len(edges) != len(permitted):
        raise ValueError("Catalog references missing edges")
    if any(e["semantics"] == "physical_membership" for e in edges):
        raise ValueError("UNSUPPORTED_RELATION: physical membership unverified")
    queue = deque([(intent["start"], [])])
    seen = {intent["start"]}
    while queue:
        node, path = queue.popleft()
        if node == intent["end"]:
            return path
        for edge in edges:
            if edge["from"] == node and edge["to"] not in seen:
                seen.add(edge["to"])
                queue.append((edge["to"], path + [edge]))
    raise ValueError("NO_SUPPORTED_PATH: " + intent_name)
