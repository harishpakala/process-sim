#!/usr/bin/env python3
"""Compare structural SHACL, engineering-aware SHACL-SPARQL, and SELiRA.

The semantic profile is a deliberately limited research comparator, not
a full translation of SELiRA's three-valued logic or evidence authority.
"""
import argparse
import json
from pathlib import Path
import sys

from rdflib import Graph, Literal, RDF
from pyshacl import validate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_selira_shacl_baseline import EX, ROOT, SHAPES, make_graph
from run_selira_e1_e10_benchmark import evaluate, synthetic_case

SEMANTIC = ROOT / "experiments" / "shacl" / "semantic-baseline.ttl"
SH = "http://www.w3.org/ns/shacl#"


def graph_with_task_scope(case_id, report=None):
    graph = make_graph(case_id, report)
    if report is None:
        sc, _ = synthetic_case(case_id)
        bundle = EX["bundle-" + case_id]
        graph.add((bundle, EX.targetRevision,
                   Literal(sc[3]["task"]["revision"])))
        graph.add((bundle, EX.targetConfiguration,
                   Literal(sc[3]["task"]["configuration"])))
    return graph


def validation(graph, shapes):
    conforms, report_graph, _ = validate(
        data_graph=graph, shacl_graph=shapes,
        inference="none", advanced=False,
        abort_on_first=False, meta_shacl=False)
    # ValidationFailure is not an RDF graph; expose the underlying failure.
    if not isinstance(report_graph, Graph):
        raise RuntimeError("pySHACL validation failed: " + str(report_graph))
    # Use explicit URIRef; count report result nodes, not duplicated triples.
    from rdflib import URIRef
    count = len(set(report_graph.subjects(
        RDF.type, URIRef(SH + "ValidationResult"))))
    return {"conforms": bool(conforms), "violations": count}


def run_case(case_id, structural, semantic, report=None):
    graph = graph_with_task_scope(case_id, report)
    combined = structural + semantic
    selira = evaluate(case_id, report)
    return {
        "id": case_id,
        "fixture": report is None,
        "rdfTripleCount": len(graph),
        "structuralSHACL": validation(graph, structural),
        "semanticSHACL": validation(graph, combined),
        "seliraSource": selira["sourceStatus"],
        "seliraCAC01": selira["decision"]["consumers"]["CAC-01"]["decision"],
        "seliraCAC02": selira["decision"]["consumers"]["CAC-02"]["decision"],
        "engineeringAuthorization": False,
    }


def build(report):
    structural = Graph().parse(SHAPES, format="turtle")
    semantic = Graph().parse(SEMANTIC, format="turtle")
    cases = [run_case("E" + str(i), structural, semantic)
             for i in range(1, 10)]
    cases.append(run_case("E10", structural, semantic, report))
    return {
        "experiment": "Structural SHACL vs semantic SHACL-SPARQL vs SELiRA",
        "engine": "pyshacl",
        "profiles": {
            "structural": str(SHAPES.relative_to(ROOT)).replace("\\", "/"),
            "semanticAdditional": str(SEMANTIC.relative_to(ROOT)).replace("\\", "/"),
        },
        "cases": cases,
        "summary": {
            "structuralConforms": sum(c["structuralSHACL"]["conforms"] for c in cases),
            "semanticConforms": sum(c["semanticSHACL"]["conforms"] for c in cases),
            "sourceV": sum(c["seliraSource"] == "V" for c in cases),
            "sourceF": sum(c["seliraSource"] == "F" for c in cases),
            "sourceU": sum(c["seliraSource"] == "U" for c in cases),
        },
        "limitations": [
            "Semantic profile includes selected engineering consistency checks, not all SELiRA source/consumer contract semantics",
            "SHACL conformance is binary and must not be interpreted as engineering authorization",
            "SHACL violation may represent missing evidence, contradiction, or consumer-specific failure",
            "Unit dimensions use a small explicit vocabulary, not a general unit ontology",
            "The synthetic evidence includes asserted verdicts, not independently authenticated engineering observations",
            "E10 GraphDB focused discovery is not upgraded to verified source assertions",
            "A more expressive SHACL profile can implement further checks; no language-level superiority is claimed",
            "Reference outcomes are scenario expectations, not independently adjudicated truth",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-semantic-shacl-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as stream:
        report = json.load(stream)
    output = build(report)
    with Path(args.output).open("w", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2)
        stream.write("\n")
    for case in output["cases"]:
        print(f'{case["id"]}: structural={case["structuralSHACL"]["conforms"]} '
              f'semantic={case["semanticSHACL"]["conforms"]} '
              f'SELiRA={case["seliraSource"]} authorization=False')
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
