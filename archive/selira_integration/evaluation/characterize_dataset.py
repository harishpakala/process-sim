"""Read-only characterization of the existing TEP NEXUS SC-01 dataset.

Run from the repository root:
    python archive/selira_integration/evaluation/characterize_dataset.py

Counts describe graph structure, not evidence-qualified admission.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, RDF

ROOT = Path(__file__).resolve().parents[3]
AI = Namespace("https://example.org/assetinventory/")
PC = Namespace("https://example.org/productcatalog/")


def characterize(directory):
    assets_graph = Graph().parse(directory / "assetinventory-instance.ttl", format="turtle")
    products_graph = Graph().parse(directory / "productcatalog-instance.ttl", format="turtle")
    assets = set(assets_graph.subjects(RDF.type, AI.Asset))
    products = set(products_graph.subjects(RDF.type, PC.Product))
    index = defaultdict(set)
    for product in products:
        for identifier in products_graph.objects(product, PC.hasProductIdentifier):
            index[str(identifier)].add(product)
    counts = Counter()
    rows = []
    for asset in sorted(assets, key=str):
        refs = {str(value) for value in assets_graph.objects(asset, AI.hasProductIdentifier)}
        matches = set().union(*(index.get(ref, set()) for ref in refs))
        category = ("unassigned" if not refs else
                    "zero_matches" if not matches else
                    "one_match" if len(matches) == 1 else "multiple_matches")
        counts[category] += 1
        rows.append({"asset": str(asset), "references": sorted(refs),
                     "matches": sorted(map(str, matches)), "category": category})
    return {
        "asset_triples": len(assets_graph),
        "catalog_triples": len(products_graph),
        "combined_triples": len(assets_graph + products_graph),
        "assets": len(assets),
        "products": len(products),
        "distinct_catalog_identifiers": len(index),
        "duplicate_catalog_identifiers": sorted(k for k, v in index.items() if len(v) > 1),
        "products_without_identifier": sum(not any(products_graph.objects(p, PC.hasProductIdentifier)) for p in products),
        "match_counts": {k: counts[k] for k in ("unassigned", "zero_matches", "one_match", "multiple_matches")},
        "assets_with_multiple_references": sum(len(row["references"]) > 1 for row in rows),
        "rows": rows,
    }


if __name__ == "__main__":
    print(json.dumps(characterize(ROOT / "semantic" / "ontology2"), indent=2))
