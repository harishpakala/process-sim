"""Regenerate integrity artifacts and verify baseline violation sets."""
import argparse
import json
from pathlib import Path

from rdflib import Graph, RDF
from rdflib.namespace import SH
from pyshacl import validate
from selira.compiler.shacl import compile_files

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT
DOMAINS = ("assetinventory", "productcatalog", "dexpi", "ecad", "engineeringbom")
EXPECTED = {"SC_01": 0, "SC_02": 9, "SC_03": 29, "SC_04": 0}


def run(output):
    data = Graph()
    for domain in DOMAINS:
        data.parse(ROOT / "datasets/tep_nexus" / (domain + "-instance.ttl"), format="turtle")
    results = {}
    for source in sorted((CONTRACTS / "contracts").glob("SC-*.safsl")):
        destination = output / source.stem
        manifest = compile_files(source, CONTRACTS / "bindings" / (source.stem + ".json"), destination)
        shapes = Graph().parse(destination / "integrity_shapes.ttl", format="turtle")
        for entry in manifest["contracts"]:
            key = entry["id"]
            name = key.replace("_", "-")
            # Isolate each shape if a specification contains multiple contracts.
            from rdflib import URIRef
            isolated = Graph()
            shape = URIRef(entry["shape"])
            for triple in shapes.triples((shape, None, None)):
                isolated.add(triple)
                if triple[1] in (SH.property, SH.sparql):
                    for child in shapes.triples((triple[2], None, None)):
                        isolated.add(child)
            _, report, _ = validate(data, shacl_graph=isolated, inference="none")
            shacl = {node for result in report.subjects(RDF.type, SH.ValidationResult)
                     for node in report.objects(result, SH.focusNode)}
            query = (destination / "sparql/standalone" / (name + ".rq")).read_text(encoding="utf-8")
            sparql = {row[0] for row in data.query(query)}
            assert sparql == shacl, (key, sorted(map(str, sparql - shacl)), sorted(map(str, shacl - sparql)))
            if key in EXPECTED:
                assert len(shacl) == EXPECTED[key], (key, len(shacl))
            results[key] = {"violations": sorted(map(str, shacl)), "equivalent": True}
    assert EXPECTED.keys() <= results.keys(), "Missing baseline contracts"
    (output / "verification.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated")
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
