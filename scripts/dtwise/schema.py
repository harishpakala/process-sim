"""DTwise schema records, focused neighborhood expansion and SHACL path extraction.

The vector search remains global. Expansion only follows the domains and
structural SHACL links of the retrieved seeds; it does not infer cross-domain
joins from a shared class such as aas:SMC.
"""
import json
from collections import defaultdict, deque
from pathlib import Path

SH = "http://www.w3.org/ns/shacl#"
STRUCTURAL = {SH + "property", SH + "node", SH + "path"}


class Schema:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.concepts = self.data.get("concepts", [])
        self.relationships = self.data.get("relationships", [])
        self.paths = self.data.get("shape_paths", [])
        self.by_uri = {c["uri"]: c for c in self.concepts if c.get("uri")}
        self.by_id = {c["id"]: c for c in self.concepts if c.get("id")}
        self.relationship_by_id = {r["id"]: r for r in self.relationships if r.get("id")}
        self.outgoing = defaultdict(list)
        self.incoming = defaultdict(list)
        for r in self.relationships:
            if r.get("subject") and r.get("object"):
                self.outgoing[r["subject"]].append(r)
                self.incoming[r["object"]].append(r)

    def records(self):
        for c in self.concepts:
            labels = c.get("labels", [])
            descriptions = c.get("descriptions", [])
            if isinstance(descriptions, str):
                descriptions = [descriptions]
            yield {
                "id": c["id"], "type": "concept", "domain": c.get("domain", ""),
                "kind": c.get("kind", ""), "uri": c["uri"],
                "labels": labels, "description": " ".join(descriptions),
                "text": f"Domain {c.get('domain', '')}. {', '.join(labels)}. "
                        f"{' '.join(descriptions)}. Kind {c.get('kind', '')}",
            }

        for r in self.relationships:
            s = self.by_uri.get(r["subject"], {})
            o = self.by_uri.get(r["object"], {})
            sl = ", ".join(s.get("labels", [])) or r["subject"].rsplit("/", 1)[-1]
            ol = ", ".join(o.get("labels", [])) or r["object"].rsplit("/", 1)[-1]
            pred = r["predicate"].rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            yield {
                "id": r["id"], "type": "relationship", "domain": r.get("domain", ""),
                "kind": "relationship", "subject": r["subject"],
                "predicate": r["predicate"], "object": r["object"],
                "text": f"Domain {r.get('domain', '')}. {sl} {pred} {ol}.",
            }

        for i, p in enumerate(self.paths):
            prop = self.by_uri.get(p.get("path"), {})
            yield {
                "id": f"shape-path:{i}", "type": "shape_path",
                "domain": p.get("domain", ""), "kind": "shape_path", **p,
                "text": f"Domain {p.get('domain', '')}. SHACL property path "
                        f"{', '.join(prop.get('labels', []))} {p.get('path', '')} "
                        f"from node shape {p.get('node_shape', '')}",
            }

    @staticmethod
    def _seed_uris(records):
        uris = set()
        for record in records:
            for key in ("uri", "subject", "object", "node_shape", "property_shape", "path"):
                if record.get(key):
                    uris.add(record[key])
        return uris

    def expand(self, records, limit=60, max_hops=2):
        """Return nearby *structural* SHACL relationships in seed domains.

        A shared target class is not traversed. Search remains global: a
        multi-domain seed set can expand independently in each seed domain.
        The limit is deterministic; direct seed edges take priority.
        """
        if limit <= 0 or max_hops <= 0 or not records:
            return []
        domains = {r.get("domain") for r in records if r.get("domain")}
        seed_uris = self._seed_uris(records)
        if not seed_uris:
            return []
        seen_uris = set(seed_uris)
        queue = deque((uri, 0) for uri in sorted(seed_uris))
        found = {}
        while queue:
            uri, depth = queue.popleft()
            if depth >= max_hops:
                continue
            # Only structural links, not sh:class or sh:targetClass.
            edges = self.outgoing.get(uri, []) + self.incoming.get(uri, [])
            for edge in edges:
                if edge.get("predicate") not in STRUCTURAL:
                    continue
                if domains and edge.get("domain") not in domains:
                    continue
                found.setdefault(edge["id"], edge)
                if len(found) >= limit:
                    return list(found.values())
                # sh:path points to a property URI, which is terminal.
                # sh:property and sh:node connect structural shape nodes.
                if edge["predicate"] not in {SH + "property", SH + "node"}:
                    continue
                for next_uri in (edge["subject"], edge["object"]):
                    if next_uri not in seen_uris:
                        seen_uris.add(next_uri)
                        queue.append((next_uri, depth + 1))
        return list(found.values())

    def shacl_paths(self, start_shape, max_depth=4, domain=None):
        """Find evidenced SHACL property chains starting at a node shape URI.

        Each hop is node_shape --sh:property--> property_shape,
        property_shape --sh:path--> predicate, optionally
        property_shape --sh:node--> next_node_shape.

        Returns paths with explicit evidence IDs. A path is schema structure,
        not an assertion that instance data exists.
        """
        if max_depth < 1:
            return []
        result = []
        queue = deque([(start_shape, [], {start_shape})])
        while queue:
            shape, chain, visited = queue.popleft()
            if len(chain) >= max_depth:
                continue
            for prop_edge in self.outgoing.get(shape, []):
                if prop_edge.get("predicate") != SH + "property":
                    continue
                if domain and prop_edge.get("domain") != domain:
                    continue
                prop_shape = prop_edge["object"]
                paths = [e for e in self.outgoing.get(prop_shape, [])
                         if e.get("predicate") == SH + "path"
                         and (not domain or e.get("domain") == domain)]
                nodes = [e for e in self.outgoing.get(prop_shape, [])
                         if e.get("predicate") == SH + "node"
                         and (not domain or e.get("domain") == domain)]
                for path_edge in paths:
                    if nodes:
                        for node_edge in nodes:
                            hop = {
                                "from_shape": shape,
                                "property_shape": prop_shape,
                                "property": path_edge["object"],
                                "to_shape": node_edge["object"],
                                "evidence_ids": [prop_edge["id"], path_edge["id"], node_edge["id"]],
                            }
                            new_chain = chain + [hop]
                            result.append(new_chain)
                            next_shape = node_edge["object"]
                            if next_shape not in visited:
                                queue.append((next_shape, new_chain, visited | {next_shape}))
                    else:
                        hop = {
                            "from_shape": shape,
                            "property_shape": prop_shape,
                            "property": path_edge["object"],
                            "to_shape": None,
                            "evidence_ids": [prop_edge["id"], path_edge["id"]],
                        }
                        result.append(chain + [hop])
        return result
