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


def _mentioned(question: str, name: str) -> bool:
    """Match whole schema identifiers, not substrings of longer identifiers."""
    return bool(name and re.search(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", question, re.I))


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
        shape_hits = []
        for uri, concept in self.shapes.items():
            labels = concept.get("labels", [])
            names = [s for s in labels if "shacl shape" not in s.casefold()]
            if any(_mentioned(question, n) for n in names):
                shape_hits.append(uri)

        prop_hits = []
        for owner, props in self.properties.items():
            for prop in props:
                candidates = (prop["name"], _short(prop["predicate"]), _short(prop["predicate"]).removeprefix("has"))
                if any(_mentioned(question, n) for n in candidates):
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


    def _shortest_path(self, start: str, target: str) -> list[dict] | None:
        """Return verified directed edges, using a bounded BFS predecessor map."""
        outgoing: dict[str, list[dict]] = defaultdict(list)
        for edge in self.edges:
            outgoing[edge["from"]].append(edge)
        queue = deque([start])
        previous: dict[str, dict | None] = {start: None}
        while queue:
            node = queue.popleft()
            if node == target:
                path = []
                while node != start:
                    edge = previous[node]
                    path.append(edge)
                    node = edge["from"]
                return list(reversed(path))
            for edge in outgoing[node]:
                if edge["to"] not in previous:
                    previous[edge["to"]] = edge
                    queue.append(edge["to"])
        return None

    def extract_grounded_question(self, question: str, connect: bool = False) -> dict:
        """Resolve explicitly mentioned parent context without inventing joins.

        For connected queries, select a shortest root-to-property-owner path
        containing the most explicitly named intermediate shapes. Equal best
        candidates remain ambiguous rather than being silently discarded.
        """
        grounded = self.ground(question)
        property_hits = grounded["properties"]
        anchors = grounded["shapes"]
        if not connect or not anchors:
            result = self.extract(anchors, [p["predicate"] for p in property_hits])
        else:
            # Named anchors which have no requested literal property are
            # potential context ancestors, not mandatory sibling targets.
            owners = {p["owner"] for p in property_hits}
            targets = sorted(owners or set(anchors))
            candidate_paths = []
            for target in targets:
                paths = []
                for start in anchors:
                    chain = self._shortest_path(start, target)
                    if chain is not None:
                        nodes = {start, target}
                        for edge in chain:
                            nodes.update((edge["from"], edge["to"]))
                        covered = len(nodes.intersection(anchors))
                        paths.append((covered, len(chain), start, chain, nodes))
                if paths:
                    candidate_paths.extend(
                        (covered, length, start, chain, nodes, target)
                        for covered, length, start, chain, nodes in paths
                    )
            if candidate_paths:
                best_coverage = max(p[0] for p in candidate_paths)
                best_length = min(p[1] for p in candidate_paths if p[0] == best_coverage)
                best = [p for p in candidate_paths if p[0] == best_coverage and p[1] == best_length]
                selected = set()
                edges = []
                for _, _, _, chain, nodes, _ in best:
                    selected.update(nodes)
                    for edge in chain:
                        if edge not in edges:
                            edges.append(edge)
                chosen_properties = [
                    p for p in property_hits if p["owner"] in selected
                ]
                result = {
                    "domain": self.domain,
                    "nodes": [
                        {"id": f"N{i}", "uri": uri,
                         "name": next((v for v in self.shapes[uri].get("labels", [])
                                       if "shacl shape" not in v.casefold()), _short(uri))}
                        for i, uri in enumerate(sorted(selected))
                    ],
                    "edges": [{"id": f"E{i}", **edge} for i, edge in enumerate(edges)],
                    "properties": [{"id": f"P{i}", **p} for i, p in enumerate(chosen_properties)],
                    "unresolved_connections": [],
                }
                if len(best) > 1:
                    result["ambiguous_paths"] = [
                        {"start": p[2], "target": p[5],
                         "nodes": sorted(p[4])} for p in best
                    ]
            else:
                result = self.extract(anchors, [p["predicate"] for p in property_hits])
                result["unresolved_connections"] = [
                    {"reason": "No verified directed path from named context to requested property owner"}
                ]
        result["question"] = question
        result["grounding"] = {
            "shape_count": len(anchors),
            "property_count": len(property_hits),
            "method": "exact-name",
        }
        return result


def load_index(path: str | Path, domain: str = "dexpi") -> SubgraphIndex:
    return SubgraphIndex.from_schema_index(json.loads(Path(path).read_text()), domain)


def extract_question(index: SubgraphIndex, question: str, connect: bool = False) -> dict:
    return index.extract_grounded_question(question, connect=connect)
