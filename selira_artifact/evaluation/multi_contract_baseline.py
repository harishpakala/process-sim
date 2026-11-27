"""Read-only RDF baseline for the four candidate SAFSL integrity contracts."""
import argparse
import hashlib
import json
from pathlib import Path

from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH
from pyshacl import validate
from selira.compiler.shacl import compile_contract
from selira.formal.identifier_comparison import compare_fields

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT
RDF_ROOT = ROOT / "datasets/tep_nexus"
PAIRS = {
    "SC-01": ("assetinventory", "productcatalog"),
    "SC-02": ("dexpi",),
    "SC-03": ("ecad",),
    "SC-04": ("engineeringbom", "productcatalog"),
}


def evaluate(sc, domains):
    source = CONTRACTS / "contracts" / (sc + ".safsl")
    binding = CONTRACTS / "bindings" / (sc + ".json")
    bindings = json.loads(binding.read_text(encoding="utf-8"))
    ttl, manifest = compile_contract(source.read_text(encoding="utf-8"), bindings)
    entry, = manifest["contracts"]
    graph = Graph()
    hashes = {}
    for domain in domains:
        path = RDF_ROOT / (domain + "-instance.ttl")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        graph.parse(path, format="turtle")
    fp = URIRef(entry["focus_predicate"])
    if entry.get("kind") == "standalone_match":
        focus = set(graph.subjects(fp, None))
        targets = set()
        left, right = map(URIRef, (entry["left_predicate"], entry["right_predicate"]))
        rows = []
        for node in sorted(focus, key=str):
            local = set(graph.objects(node, left))
            asset = set(graph.objects(node, right))
            valid = False
            if len(local) == len(asset) == 1:
                try:
                    valid = compare_fields(str(next(iter(local))), str(next(iter(asset))), entry["comparison_policy"])
                except ValueError:
                    pass
            rows.append({"focus": str(node), "left_values": sorted(map(str, local)),
                         "right_values": sorted(map(str, asset)), "conforms": valid})
        expected = {r["focus"] for r in rows if not r["conforms"]}
        metrics = {"consistent": len(focus) - len(expected), "inconsistent": len(expected)}
    else:
        tp = URIRef(entry["catalog_predicate"])
        tc = URIRef(entry["catalog_class"])
        focus = set(graph.subjects(fp, None))
        targets = set(graph.subjects(RDF.type, tc))
        index = {}
        for target in targets:
            for value in graph.objects(target, tp):
                index.setdefault(str(value), set()).add(target)
        rows = []
        for node in sorted(focus, key=str):
            refs = set(graph.objects(node, fp))
            matches = set().union(*(index.get(str(ref), set()) for ref in refs))
            rows.append({"focus": str(node), "references": sorted(map(str, refs)),
                         "reference_term_count": len(refs),
                         "matches": sorted(map(str, matches)), "match_count": len(matches)})
        expected = {r["focus"] for r in rows if r["match_count"] != 1}
        metrics = {"zero_matches": sum(r["match_count"] == 0 for r in rows),
                   "unique_matches": sum(r["match_count"] == 1 for r in rows),
                   "multiple_matches": sum(r["match_count"] > 1 for r in rows),
                   "empty_or_multivalued_references": sum(r["reference_term_count"] != 1 or
                       any(not v.strip() for v in r["references"]) for r in rows)}
    shapes = Graph().parse(data=ttl, format="turtle")
    conforms, report, _ = validate(graph, shacl_graph=shapes, inference="none",
                                    advanced=False, abort_on_first=False)
    actual = {str(n) for n in report.objects(None, SH.focusNode)}
    return {"contract": sc, "manifest": entry, "input_sha256": hashes,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "binding_sha256": hashlib.sha256(binding.read_bytes()).hexdigest(),
            "triples": len(graph), "focus_count": len(focus), "target_count": len(targets),
            **metrics,
            "focus_classes": sorted({str(t) for n in focus for t in graph.objects(n, RDF.type)}),
            "shacl_conforms": bool(conforms), "reference_violations": sorted(expected),
            "shacl_violations": sorted(actual),
            "equivalent": expected == actual and bool(conforms) == (not expected),
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/reproduced/multi_contract_baseline.json")
    args = parser.parse_args()
    results = [evaluate(sc, domains) for sc, domains in PAIRS.items()]
    assert {r["contract"]: (r["focus_count"], len(r["shacl_violations"])) for r in results} == {
        "SC-01": (38, 0), "SC-02": (39, 9), "SC-03": (40, 29), "SC-04": (71, 0)}
    payload = {"scope": "predicate-selected graph integrity only; no admission or authority qualification",
               "contracts": results, "total_focus": sum(r["focus_count"] for r in results),
               "all_equivalent": all(r["equivalent"] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for r in results:
        print(r["contract"], "focus=", r["focus_count"], "violations=", len(r["shacl_violations"]),
              "SHACL=", r["shacl_conforms"], "equivalent=", r["equivalent"])
    print("Total focus:", payload["total_focus"], "All equivalent:", payload["all_equivalent"])
    print("Results:", args.output)
    return 0 if payload["all_equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
