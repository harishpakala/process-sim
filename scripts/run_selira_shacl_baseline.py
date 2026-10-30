#!/usr/bin/env python3
"""Run actual pySHACL Core validation on RDF encodings of E1-E10 inputs.

Install: python -m pip install "rdflib>=7,<9" "pyshacl>=0.30,<1"
SHACL conformance is not an engineering acceptance decision.
"""
import argparse
import json
from pathlib import Path
import sys

from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
from pyshacl import validate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_selira_e1_e10_benchmark import evaluate, synthetic_case

EX = Namespace("urn:selira:shacl:")
ROOT = Path(__file__).resolve().parents[1]
SHAPES = ROOT / "experiments" / "shacl" / "structural-baseline.ttl"


def make_graph(case_id, report=None):
    """Encode input assertions, not evaluator verdicts, as RDF."""
    graph = Graph()
    graph.bind("ex", EX)
    bundle = EX["bundle-" + case_id]
    graph.add((bundle, RDF.type, EX.EvidenceBundle))
    if report is not None:
        # Preserve source RDF observations as separate evidence, without
        # upgrading them to authenticated contract assertions.
        for i, fact in enumerate(report.get("facts", [])):
            if not isinstance(fact, dict):
                continue
            obs = EX["discovery-" + str(i)]
            graph.add((obs, RDF.type, EX.DiscoveryObservation))
            for key in ("s", "p", "o", "g"):
                if isinstance(fact.get(key), str):
                    graph.add((obs, EX["rdf_" + key], Literal(fact[key])))
        return graph

    sc, cac = synthetic_case(case_id)
    for assertion in sc[0]["assertions"]:
        node = BNode()
        graph.add((bundle, EX.identityLink, node))
        graph.add((node, EX.fromRole, Literal(assertion["fromRole"])))
        graph.add((node, EX.toRole, Literal(assertion["toRole"])))
        graph.add((node, EX.assertedVerdict, Literal(assertion["verdict"])))
        graph.add((node, EX.revision, Literal(assertion["revision"])))
    for assertion in sc[1]["quantityAssertions"]:
        pred = (EX.engineeringQuantity if assertion["side"] == "engineering"
                else EX.operationalQuantity)
        graph.add((bundle, pred, Literal(assertion["quantityKind"])))
    for assertion in sc[2]["unitAssertions"]:
        pred = (EX.engineeringUnit if assertion["side"] == "engineering"
                else EX.operationalUnit)
        graph.add((bundle, pred, Literal(assertion["unit"])))
    for assertion in sc[3]["applicabilityAssertions"]:
        node = BNode()
        graph.add((bundle, EX.applicability, node))
        graph.add((node, EX.revision, Literal(assertion["revision"])))
        graph.add((node, EX.configuration, Literal(assertion["configuration"])))
        graph.add((node, EX.assertedVerdict, Literal(assertion["verdict"])))
    for assertion in sc[4]["bindingAssertions"]:
        node = BNode()
        graph.add((bundle, EX.binding, node))
        graph.add((node, EX.nodeId, Literal(assertion["nodeId"])))
        graph.add((node, EX.assertedVerdict, Literal(assertion["verdict"])))
    for contract, predicate in (("CAC-01", EX.cac01Check),
                                ("CAC-02", EX.cac02Check)):
        for assertion in cac[contract]["checks"]:
            node = BNode()
            graph.add((bundle, predicate, node))
            graph.add((node, EX.requirement, Literal(assertion["requirement"])))
            graph.add((node, EX.assertedVerdict, Literal(assertion["verdict"])))
    return graph


def run_case(case_id, shapes, report=None):
    graph = make_graph(case_id, report)
    conforms, report_graph, report_text = validate(
        data_graph=graph, shacl_graph=shapes, inference="none",
        advanced=False, abort_on_first=False, meta_shacl=False)
    violations = list(report_graph.subjects(RDF.type,
                                            URIRef("http://www.w3.org/ns/shacl#ValidationResult")))
    selira = evaluate(case_id, report)
    return {
        "id": case_id,
        "fixture": report is None,
        "rdfTripleCount": len(graph),
        "shaclConforms": bool(conforms),
        "shaclViolationCount": len(violations),
        "seliraSource": selira["sourceStatus"],
        "seliraCAC01": selira["decision"]["consumers"]["CAC-01"]["decision"],
        "seliraCAC02": selira["decision"]["consumers"]["CAC-02"]["decision"],
        "engineeringAuthorization": False,
    }


def build(report):
    shapes = Graph().parse(SHAPES, format="turtle")
    rows = [run_case("E" + str(i), shapes) for i in range(1, 10)]
    rows.append(run_case("E10", shapes, report))
    return {
        "experiment": "SHACL Core structural validation vs SELiRA",
        "engine": "pyshacl",
        "shapeFile": str(SHAPES.relative_to(ROOT)).replace("\\", "/"),
        "cases": rows,
        "summary": {
            "shaclConforms": sum(row["shaclConforms"] for row in rows),
            "shaclNonconforms": sum(not row["shaclConforms"] for row in rows),
            "seliraSourceV": sum(row["seliraSource"] == "V" for row in rows),
            "seliraSourceF": sum(row["seliraSource"] == "F" for row in rows),
            "seliraSourceU": sum(row["seliraSource"] == "U" for row in rows),
        },
        "limitations": [
            "This is a real pySHACL execution but only a deliberately scoped SHACL Core structural shape",
            "SHACL nonconformance is not identical to source F; missing evidence yields SELiRA U",
            "SHACL conformance is not engineering acceptance, authentication, or authorization",
            "RDF is generated from the same synthetic input assertions, not from SELiRA verdicts",
            "E10 contains actual focused GraphDB discovery observations, not independently authenticated contract assertions",
            "More expressive SHACL/SPARQL shapes could detect additional contradictions",
            "No claim of superiority over SHACL as a language or existing SHACL applications",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-shacl-baseline-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as stream:
        report = json.load(stream)
    payload = build(report)
    with Path(args.output).open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    for row in payload["cases"]:
        print(f'{row["id"]}: SHACL={row["shaclConforms"]} '
              f'SELiRA={row["seliraSource"]} authorization=False')
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
