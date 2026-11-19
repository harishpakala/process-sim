"""Query-time SHACL subgraph extraction from the existing DTWise schema index.

No LLM or SPARQL generation here. This module grounds exact schema labels,
preserves ambiguous candidates, and extracts verified edges without
enumerating all paths. Works for any single domain; DEXPI is the first fixture.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

SH_NODE = "http://www.w3.org/ns/shacl#node"
SH_NODE_SHAPE = "http://www.w3.org/ns/shacl#NodeShape"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _short(uri: str) -> str:
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


@dataclass
class SubgraphIndex:
    """Cached domain-specific adjacency and property ownership indexes."""

    domain: str
    shapes: dict[str, dict]
    properties: dict[str, list[dict]]
    edges: list[dict]

    @classmethod
    def from_schema_index(cls, schema: dict, domain: str) -> "SubgraphIndex":
        concepts = [c for c in schema["concepts"] if c.get("domain") == domain]
        shapes = {
            c["uri"]: c for c in concepts
            if SH_NODE_SHAPE in c.get("types", [])
        }
        property_nodes = {c["uri"]: c for c in concepts}
        node_targets: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for rel in schema["relationships"]:
            if rel.get("domain") == domain and rel.get("predicate") == SH_NODE:
                if rel["object"] in shapes:
                    node_targets[rel["subject"]].append((rel["object"], rel["id"]))

        properties: dict[str, list[dict]] = defaultdict(list)
        edges: list[dict] = []
        for path in schema["shape_paths"]:
            if path.get("domain") != domain or path["node_shape"] not in shapes:
                continue
            owner, prop_shape = path["node_shape"], path["property_shape"]
            pred = path["path"]
            evidence = list(path.get("evidence", []))
            targets = node_targets.get(prop_shape, [])
            if targets:
                for target, node_evidence in targets:
                    edges.append({
                        "from": owner, "to": target, "predicate": pred,
                        "property_shape": prop_shape,
                        "evidence": sorted(set(evidence + [node_evidence])),
                    })
            else:
                pc = property_nodes.get(prop_shape, {})
                labels = pc.get("labels", [])
                properties[owner].append({
                    "owner": owner, "predicate": pred,
                    "property_shape": prop_shape,
                    "name": next((v for v in labels if not v.endswith(" constraint")), _short(pred).removeprefix("has")),
                    "evidence": evidence,
                })
        return cls(domain, shapes, dict(properties), edges)

    def ground(self, question: str) -> dict:
        """Exact phrase matches only; no unverified semantic inference."""
        q = question.casefold()
        compact = _norm(question)
        shape_hits = []
        for uri, concept in self.shapes.items():
            labels = concept.get("labels", [])
            names = [s for s in labels if "shacl shape" not in s.casefold()]
            if any(_norm(n) and _norm(n) in compact for n in names):
                shape_hits.append(uri)

        prop_hits = []
        for owner, props in self.properties.items():
            for prop in props:
                candidates = (prop["name"], _short(prop["predicate"]), _short(prop["predicate"]).removeprefix("has"))
                if any(_norm(n) and _norm(n) in compact for n in candidates):
                    prop_hits.append(prop)
        # If only properties are mentioned, their owners become candidate shapes.
        return {"shapes": sorted(set(shape_hits) | {p["owner"] for p in prop_hits}),
                "properties": prop_hits}

    def extract(
        self, shape_uris: list[str], property_predicates: list[str] | None = None,
        connect: bool = False, max_nodes: int = 64,
    ) -> dict:
        """Extract anchor fragments, optionally adding shortest verified connections.

        connect=False preserves independent components. connect=True joins each
        reachable anchor to the first anchor using directed SHACL edges; it
        does not assert that the user intended those joins.
        """
        if any(uri not in self.shapes for uri in shape_uris):
            raise ValueError("Unknown or non-NodeShape anchor")
        anchors = list(dict.fromkeys(shape_uris))
        selected = set(anchors)
        chosen_edges: list[dict] = []
        outgoing: dict[str, list[dict]] = defaultdict(list)
        for edge in self.edges:
            outgoing[edge["from"]].append(edge)
        unresolved = []
        if connect and len(anchors) > 1:
            root = anchors[0]
            for target in anchors[1:]:
                queue = deque([(root, [])])
                seen = {root}
                found = None
                while queue:
                    node, chain = queue.popleft()
                    if node == target:
                        found = chain
                        break
                    for edge in outgoing[node]:
                        nxt = edge["to"]
                        if nxt not in seen:
                            seen.add(nxt)
                            queue.append((nxt, chain + [edge]))
                if found is None:
                    unresolved.append({"from": root, "to": target})
                else:
                    for edge in found:
                        selected.update((edge["from"], edge["to"]))
                        if edge not in chosen_edges:
                            chosen_edges.append(edge)
                if len(selected) > max_nodes:
                    raise ValueError("Subgraph node budget exceeded")

        requested = set(property_predicates or [])
        chosen_properties = [
            p for owner in selected for p in self.properties.get(owner, [])
            if not requested or p["predicate"] in requested
        ]
        # A predicate may have several owners; keep every owner.
        return {
            "domain": self.domain,
            "nodes": [
                {"id": f"N{i}", "uri": uri,
                 "name": next((s for s in self.shapes[uri].get("labels", [])
                               if "shacl shape" not in s.casefold()), _short(uri))}
                for i, uri in enumerate(sorted(selected))
            ],
            "edges": [
                {"id": f"E{i}", **edge} for i, edge in enumerate(chosen_edges)
            ],
            "properties": [
                {"id": f"P{i}", **prop} for i, prop in enumerate(chosen_properties)
            ],
            "unresolved_connections": unresolved,
        }


def load_index(path: str | Path, domain: str = "dexpi") -> SubgraphIndex:
    return SubgraphIndex.from_schema_index(json.loads(Path(path).read_text()), domain)


def extract_question(index: SubgraphIndex, question: str, connect: bool = False) -> dict:
    grounded = index.ground(question)
    result = index.extract(
        grounded["shapes"],
        [p["predicate"] for p in grounded["properties"]],
        connect=connect,
    )
    result["question"] = question
    result["grounding"] = {
        "shape_count": len(grounded["shapes"]),
        "property_count": len(grounded["properties"]),
        "method": "exact-name",
    }
    return result
