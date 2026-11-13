#!/usr/bin/env python3
"""Phase 6C: read-only relationship evidence inventory from full SHACL/OWL schema.

A SHACL value_class provides a declared type constraint, NOT instance-level
evidence of an asserted relationship. Never promote equality-join hypotheses
to verified engineering identity or physical membership.
"""
import argparse
import json
from pathlib import Path

try:
    from experiments.q13_extract_focused_schema import ROOT, extract
except ModuleNotFoundError as exc:
    if exc.name != "experiments":
        raise
    from q13_extract_focused_schema import ROOT, extract


def inventory(schema):
    domains = schema.get("domains") or []
    shapes = [
        {"domain": domain["domain"], **shape}
        for domain in domains for shape in domain.get("node_shapes", [])
    ]
    by_class = {}
    for shape in shapes:
        for cls in shape.get("target_classes", []):
            by_class.setdefault(cls, []).append({
                "domain": shape["domain"], "shape": shape["uri"]})
    edges = []
    for source in shapes:
        for prop in source.get("properties", []):
            if prop.get("kind") != "object" and not prop.get("value_class"):
                continue
            target = prop.get("value_class")
            matches = sorted(by_class.get(target, []),
                             key=lambda x: (x["domain"], x["shape"])) if target else []
            edges.append({
                "source_domain": source["domain"],
                "source_shape": source["uri"],
                "predicate": prop["predicate"],
                "direction": "forward",
                "property_kind": prop.get("kind"),
                "declared_value_class": target,
                "target_shape_candidates": matches,
                "declaration_status": (
                    "shacl_class_constraint_with_target_shape_candidates" if matches
                    else "shacl_class_constraint_without_matching_target_shape" if target
                    else "object_property_without_shacl_target_class"
                ),
                "instance_triple_verified": False,
                "cross_domain_identity_verified": False,
                "physical_membership_verified": False,
                "eligible_for_verified_traversal": False,
            })
    requested = [
        "https://example.org/ecad/hasPLCEndPoint",
        "https://example.org/productcatalog/hasIRDI",
        "https://example.org/productcatalog/hasQuDTAttribute",
        "https://example.org/productcatalog/hasCatalogTechnicalSpecification",
        "https://example.org/productcatalog/hasCrossDomainAssociationEvidence",
        "https://example.org/ecad/hasAssetIdentifier",
    ]
    occurrences = {}
    for predicate in requested:
        occurrences[predicate] = sorted([
            {"domain": shape["domain"], "shape": shape["uri"],
             "kind": prop.get("kind"), "value_class": prop.get("value_class")}
            for shape in shapes for prop in shape.get("properties", [])
            if prop.get("predicate") == predicate
        ], key=lambda x: (x["domain"], x["shape"]))
    return {
        "method": "phase6c_full_shacl_declaration_inventory",
        "schema_sources": [{"domain": d["domain"], "file": d.get("source_file"),
                            "sha256": d.get("source_sha256")} for d in domains],
        "relationship_declarations": edges,
        "investigated_predicates": occurrences,
        "identifier_equality_hypotheses": schema.get("cross_domain_identifier_candidates", []),
        "limitations": [
            "SHACL class constraints describe allowed target types, not observed graph triples.",
            "OWL ObjectProperty declaration alone does not establish domain/range or a verified join.",
            "Complex SHACL paths were omitted by upstream extraction.",
            "No GraphDB instance evidence has been inspected.",
            "Functional association, identifier equality, and recorded parent context are not physical membership.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("reports/phase6_relationship_inventory.json"))
    args = parser.parse_args()
    result = inventory(extract())
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print("Inventory:", path)
    print("SHACL relationship declarations:", len(result["relationship_declarations"]))
    for predicate, owners in result["investigated_predicates"].items():
        print(predicate, "full-schema shape declarations:", len(owners))
    print("Verified instance paths: 0 (not assessed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
