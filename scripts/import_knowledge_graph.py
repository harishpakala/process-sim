#!/usr/bin/env python3
"""Lift configured AAS template/instance pairs and optionally publish their RDF graphs.

Run from the repository root:
    python3 scripts/import_knowledge_graph.py
    python3 scripts/import_knowledge_graph.py --push
    python3 scripts/import_knowledge_graph.py --push --validate

Source of truth: semantic/config.py TARGETS.
Does not use scripts/export_asset_kg.py or fabricated RDF classes.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic.config import TARGETS, OUTPUT
from semantic import template_lifting, instance_lifting
from semantic.ontoutils import compute_uri, push_graph_to_graphdb


def lift_domain(domain, template_path, instance_path, validate=False, push=False):
    with Path(template_path).open(encoding="utf-8") as source:
        template = template_lifting.aas_jsonization.submodel_from_jsonable(json.load(source))
    instance = instance_lifting.load_submodel(str(instance_path))

    template_graph = template_lifting.build_template_graph(template, domain)
    instance_lifting.REPEATABLE_COLLECTIONS.clear()
    instance_lifting.REPEATABLE_COLLECTIONS.update(
        instance_lifting.infer_repeatable_collections(template)
    )
    instance_graph = instance_lifting.build_instance_graph(instance, domain, template.id)

    if validate:
        instance_lifting.validate_instance(
            instance_graph, template_graph, compute_uri(instance.id, "")
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    template_dest = OUTPUT / f"{domain}-template.ttl"
    instance_dest = OUTPUT / f"{domain}-instance.ttl"
    template_graph.serialize(destination=str(template_dest), format="turtle")
    instance_graph.serialize(destination=str(instance_dest), format="turtle")
    print(f"[OK] {domain}: {len(template_graph)} template triples, {len(instance_graph)} instance triples")

    if push:
        # Publish template before its instance, preserving established named-graph URIs.
        push_graph_to_graphdb(template_graph, compute_uri(template.id))
        push_graph_to_graphdb(instance_graph, compute_uri(instance.id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true", help="Publish to configured GraphDB AAS repository")
    parser.add_argument("--validate", action="store_true", help="Validate instance graphs against lifted SHACL")
    args = parser.parse_args()
    failures = []
    for domain, template_path, instance_path in TARGETS:
        try:
            lift_domain(domain, template_path, instance_path, validate=args.validate, push=args.push)
        except Exception as exc:
            print(f"[FAILED] {domain}: {exc}", file=sys.stderr)
            failures.append(domain)
    if failures:
        raise SystemExit("Semantic lifting failed for: " + ", ".join(failures))
    print("All configured AAS domains lifted successfully.")


if __name__ == "__main__":
    main()
