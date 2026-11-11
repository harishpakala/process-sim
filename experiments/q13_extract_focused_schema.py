#!/usr/bin/env python3
"""Extract a compact, auditable schema from six SHACL/OWL TTL templates.

No instance data, reference query, or expected answer is read.
Run: python experiments/q13_extract_focused_schema.py
Optional: --output reports/q13_focused_schema.json
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, SH, OWL

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "semantic" / "ontology"
FILES = {
    "dexpi": "dexpi-template.ttl",
    "ecad": "ecad-template.ttl",
    "engineeringbom": "ebom_v2_shapes.ttl",
    "assetinventory": "assetinventory-template.ttl",
    "opcuaconnectivity": "opcuaconnectivity-template.ttl",
    "productcatalog": "productcatalog-template.ttl",
}
IDENTIFIERS = ("hasAssetIdentifier", "hasProductIdentifier")


def label(graph, node):
    value = graph.value(node, RDFS.label)
    return str(value) if value is not None else None


def annotation(graph, node, predicate):
    values = sorted(str(value) for value in graph.objects(node, predicate))
    return values[0] if values else None


def extract():
    domains = []
    by_identifier = defaultdict(list)
    for domain, filename in FILES.items():
        data = (BASE / filename).read_bytes()
        graph = Graph()
        graph.parse(data=data.decode("utf-8"), format="turtle")
        classes = sorted(
            [{"uri": str(subject), "label": label(graph, subject)}
             for subject in set(graph.subjects(RDF.type, OWL.Class))],
            key=lambda item: item["uri"],
        )
        shapes = []
        valid_predicates = set()
        for node in set(graph.subjects(RDF.type, SH.NodeShape)):
            properties = []
            for prop in set(graph.objects(node, SH.property)):
                path = graph.value(prop, SH.path)
                if not isinstance(path, URIRef):
                    continue  # Only direct URI SHACL paths; complex paths not flattened.
                valid_predicates.add(str(path))
                kind = ("object" if (path, RDF.type, OWL.ObjectProperty) in graph
                        else "datatype" if (path, RDF.type, OWL.DatatypeProperty) in graph
                        else "unspecified")
                item = {"predicate": str(path),
                        "label": annotation(graph, prop, SH.name) or label(graph, prop),
                        "description": annotation(graph, prop, SH.description) or annotation(graph, path, RDFS.comment),
                        "kind": kind}
                datatype = graph.value(prop, SH.datatype)
                node_kind = graph.value(prop, SH.nodeKind)
                target_class = graph.value(prop, SH["class"])
                if datatype is not None:
                    item["datatype"] = str(datatype)
                if node_kind is not None:
                    item["node_kind"] = str(node_kind)
                if target_class is not None:
                    item["value_class"] = str(target_class)
                nested_shape = graph.value(prop, SH.node)
                if nested_shape is not None:
                    item["node_shape"] = str(nested_shape)
                properties.append(item)
                local = str(path).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                if local in IDENTIFIERS:
                    by_identifier[local].append({
                        "domain": domain, "predicate": str(path),
                        "parent_shape": str(node),
                        "parent_shape_label": label(graph, node),
                    })
            if properties:
                shapes.append({
                    "uri": str(node),
                    "label": annotation(graph, node, SH.name) or label(graph, node),
                    "description": annotation(graph, node, SH.description),
                    "target_classes": sorted(str(v) for v in graph.objects(node, SH.targetClass)),
                    "properties": sorted(properties, key=lambda item: item["predicate"]),
                })
        domains.append({
            "domain": domain, "source_file": filename,
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "classes": classes,
            "node_shapes": sorted(shapes, key=lambda item: item["uri"]),
            "valid_predicates": sorted(valid_predicates),
        })
    # Matching property local names are candidate equality joins, not OWL axioms.
    candidates = []
    for name, occurrences in sorted(by_identifier.items()):
        if len({item["domain"] for item in occurrences}) < 2:
            continue
        candidates.append({
            "identifier": name.removeprefix("has"),
            "evidence": "same SHACL predicate local name in multiple domains",
            "status": "candidate_value_equality_join_not_formally_asserted",
            "semantics": "Join on equal RDF terms only when identifiers have matching meaning and representation.",
            "occurrences": sorted(occurrences, key=lambda item: item["domain"]),
        })
    return {
        "method": "schema_only_shacl_owl_extraction",
        "limitations": [
            "Cross-domain equality joins are candidates inferred from property naming; TTL SHACL paths alone do not prove identifier equivalence.",
            "Complex SHACL paths are not flattened.",
            "No instance data or expected answer is included.",
        ],
        "domains": domains,
        "cross_domain_identifier_candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/q13_focused_schema.json")
    args = parser.parse_args()
    result = extract()
    path = Path(args.output)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Wrote", path)
    for domain in result["domains"]:
        print(domain["domain"], "classes:", len(domain["classes"]),
              "shapes:", len(domain["node_shapes"]),
              "valid predicates:", len(domain["valid_predicates"]))
    for item in result["cross_domain_identifier_candidates"]:
        print("Candidate", item["identifier"], ":", ", ".join(
            x["domain"] for x in item["occurrences"]))


if __name__ == "__main__":
    main()
