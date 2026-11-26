"""Read-only, binding-driven characterization of TEP NEXUS RDF instances."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, RDF, URIRef

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("assetinventory", "productcatalog", "dexpi",
           "opcuaconnectivity", "engineeringbom")


def characterize(directory, bindings):
    graph = Graph()
    datasets = {}
    hashes = {}
    for domain in DOMAINS:
        path = directory / (domain + "-instance.ttl")
        part = Graph().parse(path, format="turtle")
        datasets[domain] = len(part)
        graph += part
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    contracts = {}
    dependencies = defaultdict(lambda: defaultdict(list))
    for path in sorted(bindings.glob("SC-*.json")):
        hashes["bindings/" + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        templates = list(json.loads(path.read_text(encoding="utf-8"))["templates"].values())
        sources = [t for t in templates if t.get("target_by_predicate")]
        targets = [t for t in templates if t.get("lexical_match")]
        if len(templates) != 2 or len(sources) != 1 or len(targets) != 1:
            raise ValueError(f"Unsupported binding structure: {path}")
        source, target = sources[0], targets[0]
        if source is target or len(source["fields"]) != 1 or len(target["fields"]) != 1:
            raise ValueError(f"Expected distinct single-field bindings: {path}")
        fp = URIRef(next(iter(source["fields"].values())))
        tp = URIRef(next(iter(target["fields"].values())))
        tc = URIRef(target["class"])
        focus = set(graph.subjects(fp, None))
        typed = set(graph.subjects(RDF.type, URIRef(source["class"])))
        population = set(graph.subjects(RDF.type, tc))
        index = defaultdict(set)
        target_rows = []
        for node in sorted(population, key=str):
            terms = set(graph.objects(node, tp))
            values = sorted({str(v) for v in terms})
            target_rows.append({"resource": str(node), "identifiers": values,
                                "term_count": len(terms)})
            for value in values:
                index[value].add(node)
        rows = []
        scope = (str(tc), str(tp))
        for node in sorted(focus, key=str):
            terms = set(graph.objects(node, fp))
            values = sorted({str(v) for v in terms})
            matches = set().union(*(index.get(v, set()) for v in values))
            rows.append({"resource": str(node), "identifiers": values,
                         "term_count": len(terms), "matches": sorted(map(str, matches)),
                         "match_count": len(matches)})
            for value in values:
                dependencies[scope][value].append({"contract": path.stem, "resource": str(node)})
        contracts[path.stem] = {
            "source_predicate": str(fp), "target_predicate": str(tp),
            "target_class": str(tc), "focus_count": len(focus),
            "source_metadata_class_count": len(typed),
            "metadata_class_without_reference": sorted(map(str, typed - focus)),
            "focus_outside_metadata_class": sorted(map(str, focus - typed)),
            "target_count": len(population), "distinct_target_identifiers": len(index),
            "duplicate_identifiers": sorted(v for v, nodes in index.items() if len(nodes) > 1),
            "match_counts": {str(n): sum(r["match_count"] == n for r in rows) for n in sorted({0, 1} | {r["match_count"] for r in rows})},
            "sources": rows, "targets": target_rows,
            "unreferenced_target_identifiers": sorted(set(index) - {v for r in rows for v in r["identifiers"]}),
        }
        for value in index:
            dependencies[scope][value]
    if not contracts:
        raise ValueError("No SC binding files found")
    shared = []
    for (tc, tp), values in sorted(dependencies.items()):
        for value, refs in sorted(values.items()):
            counts = {c: sum(r["contract"] == c for r in refs)
                      for c in sorted({r["contract"] for r in refs})}
            shared.append({"target_class": tc, "target_predicate": tp,
                           "identifier": value, "reference_count": len(refs),
                           "counts_by_contract": counts,
                           "shared_across_contracts": len(counts) > 1,
                           "references": refs})
    return {"scope": "Structural characterization; lexical matching; not evidence qualification",
            "dataset_triples": datasets, "union_triples": len(graph),
            "input_sha256": hashes, "total_focus": sum(c["focus_count"] for c in contracts.values()),
            "contracts": contracts, "identifier_dependencies": shared}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT.parent / "semantic/ontology2")
    parser.add_argument("--bindings", type=Path, default=ROOT / "bindings")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/reproduced/tep_nexus_characterization.json")
    args = parser.parse_args()
    report = characterize(args.dataset, args.bindings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Union triples:", report["union_triples"])
    for name, c in report["contracts"].items():
        print(name, "focus:", c["focus_count"], "targets:", c["target_count"], "matches:", c["match_counts"])
    print("Total contract instances:", report["total_focus"])
    print("Shared identifiers:", sum(r["shared_across_contracts"] for r in report["identifier_dependencies"]))
    print("Results:", args.output)


if __name__ == "__main__":
    main()
