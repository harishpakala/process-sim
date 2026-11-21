"""Evidence-only cross-domain equality grounding for SHACL Phase-1 planning.

A common property name is not a SHACL edge. This module identifies pairs of
directly owned SHACL properties that *could* support an explicit equality match.
It never asserts that values match in the data, or that a cross-domain SHACL
relationship exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from .subgraph import SubgraphIndex, _short


@dataclass
class MultiDomainGrounding:
    indexes: dict[str, SubgraphIndex]

    @classmethod
    def load(cls, schema_path: str | Path, domains: list[str]):
        if len(domains) < 2 or len(domains) != len(set(domains)):
            raise ValueError("Supply at least two distinct domains")
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        return cls({domain: SubgraphIndex.from_schema_index(schema, domain)
                    for domain in domains})

    def property_matches(self, property_name: str, owners: dict[str, set[str]]):
        """Find directly owned matching properties in each requested domain.

        owners maps domain -> explicit SHACL NodeShape URI anchors. A pair is
        returned only when each side has exactly one grounded owner/property.
        Ambiguity is reported, never silently resolved.
        """
        if set(owners) != set(self.indexes):
            raise ValueError("Each requested domain must supply explicit shape anchors")
        matches = {}
        for domain, index in self.indexes.items():
            candidates = []
            for owner in sorted(owners[domain]):
                if owner not in index.shapes:
                    raise ValueError(f"Unknown shape in {domain}: {owner}")
                for prop in index.properties.get(owner, []):
                    labels = {prop["name"].casefold(),
                              _short(prop["predicate"]).casefold(),
                              _short(prop["predicate"]).removeprefix("has").casefold()}
                    if property_name.casefold() in labels:
                        candidates.append({
                            "domain": domain,
                            "owner": owner,
                            "predicate": prop["predicate"],
                            "property_shape": prop["property_shape"],
                            "evidence": list(prop["evidence"]),
                        })
            matches[domain] = candidates
        if any(len(values) != 1 for values in matches.values()):
            return {"status": "ambiguous" if all(matches.values()) else "unresolved",
                    "candidates": matches, "equality": None}
        return {
            "status": "grounded",
            "candidates": matches,
            "equality": {
                "operator": "=",
                "sides": [matches[domain][0] for domain in self.indexes],
                "basis": "explicit equality request and two SHACL-owned properties",
                "shacl_cross_domain_edge": False,
            },
        }
