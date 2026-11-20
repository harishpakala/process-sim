"""Read-only audit of SHACL identifier owners versus approved mapping evidence.

Run: python -m process_sim.dtwise.experimental_shacl_owner_evidence_audit
This reports property ownership and evidence overlap; it NEVER approves pairs.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex

DOMAINS = frozenset(("dexpi", "ecad", "assetinventory"))


def audit(schema: dict, mappings: dict[str, dict]) -> list[dict]:
    indexes = {domain: SubgraphIndex.from_schema_index(schema, domain)
               for domain in sorted(DOMAINS)}
    records = []
    for mapping in sorted(mappings.values(), key=lambda m: m["id"]):
        if {mapping["left_domain"], mapping["right_domain"]} - DOMAINS:
            continue
        sides = {}
        for side in ("left", "right"):
            domain = mapping[f"{side}_domain"]
            predicate = mapping[f"{side}_property"]
            owners = []
            for owner, properties in sorted(indexes[domain].properties.items()):
                for prop in properties:
                    if prop["predicate"] != predicate:
                        continue
                    names = indexes[domain].shapes[owner].get("labels", [])
                    evidence = set(prop["evidence"])
                    owners.append({
                        "owner_shape_uri": owner,
                        "owner_labels": names,
                        "property_shape_uri": prop["property_shape"],
                        "predicate": predicate,
                        "shacl_evidence_ids": sorted(evidence),
                        "mapping_evidence_overlap": sorted(
                            evidence.intersection(mapping["evidence_ids"])
                        ),
                    })
            sides[side] = owners
        records.append({
            "mapping_id": mapping["id"],
            "mapping_verified_at_property_level": mapping.get("verified") is True,
            "approved_owner_pairs": mapping.get("approved_owner_pairs", []),
            "left_owners": sides["left"],
            "right_owners": sides["right"],
            "owner_pair_approval_inferred": False,
        })
    return records


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    print(json.dumps(audit(schema, mappings), indent=2, ensure_ascii=False))
    print("Evidence overlap is NOT cross-domain owner-pair approval.")


if __name__ == "__main__":
    main()
