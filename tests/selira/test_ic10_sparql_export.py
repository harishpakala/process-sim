"""Bounded differential tests for standalone SPARQL export."""
import base64
import itertools
import json

import pytest
from rdflib import Graph, Literal, Namespace, RDF
from rdflib.namespace import SH
from pyshacl import validate
from process_sim.safsl.shacl.compiler import compile_files


@pytest.mark.parametrize("namespace,contract", [
    ("urn:example:original:", "SC_01"),
    ("https://example.net/renamed/", "RenamedRule"),
])
@pytest.mark.parametrize("kind", ["reference", "identifier"])
def test_export_equivalence(tmp_path, namespace, contract, kind):
    ns = Namespace(namespace)
    encode = lambda value: base64.b64encode(str(value).encode()).decode()
    templates = {
        str(ns.SourceTemplate): {
            "class": str(ns.Source), "target_by_predicate": True,
            "fields": {"Left": str(ns.left), "Right": str(ns.right)},
        },
        str(ns.TargetTemplate): {
            "class": str(ns.Target), "fields": {"Key": str(ns.key)},
            "lexical_match": True,
        },
    }
    if kind == "identifier":
        templates[str(ns.SourceTemplate)]["comparison_policy"] = {
            "kind": "normalized_asset_identifier", "exceptions": []}
        rule = "matches(s.Left, s.Right);"
    else:
        rule = "existsExactlyOne t in targets where matches(s.Left, t.Key);"
    source = (
        'Specification Example { Ref SubmodelTemplate sources = "'
        + encode(ns.SourceTemplate) + '"; Ref SubmodelTemplate targets = "'
        + encode(ns.TargetTemplate) + '"; Contract ' + contract
        + ' { forall s in sources { ' + rule + ' } } }'
    )
    src, bindings = tmp_path / "input.safsl", tmp_path / "bindings.json"
    src.write_text(source, encoding="utf-8")
    bindings.write_text(json.dumps({"templates": templates}), encoding="utf-8")
    out = tmp_path / "generated"
    compile_files(src, bindings, out)
    shapes = Graph().parse(out / "integrity_shapes.ttl", format="turtle")
    name = contract.replace("_", "-")
    exact = (out / "sparql/shacl" / (name + ".rq")).read_text()
    assert exact.strip() == str(next(shapes.objects(None, SH.select))).strip()
    query = (out / "sparql/standalone" / (name + ".rq")).read_text()
    values = [(), ("A",), ("B",), ("A", "B")]
    assets = [(), ("https://assets.example/A",), ("https://assets.example/B",),
              ("https://assets.example/A", "https://assets.example/B")]
    cases = itertools.product(values, assets) if kind == "identifier" else itertools.product(values, values, values)
    for case in cases:
        graph = Graph()
        graph.add((ns.focus, RDF.type, ns.Source))
        for value in case[0]:
            graph.add((ns.focus, ns.left, Literal(value)))
        if kind == "identifier":
            for value in case[1]:
                graph.add((ns.focus, ns.right, Literal(value)))
            expected = bool(case[1]) and not (
                len(case[0]) == len(case[1]) == 1
                and case[0][0] == case[1][0].rsplit("/", 1)[-1])
        else:
            for node, keys in zip((ns.target1, ns.target2), case[1:]):
                graph.add((node, RDF.type, ns.Target))
                for value in keys:
                    graph.add((node, ns.key, Literal(value)))
            expected = bool(case[0]) and sum(bool(set(case[0]) & set(keys)) for keys in case[1:]) != 1
        _, report, _ = validate(graph, shacl_graph=shapes, inference="none")
        shacl = {node for result in report.subjects(RDF.type, SH.ValidationResult)
                 for node in report.objects(result, SH.focusNode)}
        sparql = {row[0] for row in graph.query(query)}
        assert sparql == shacl == ({ns.focus} if expected else set()), (kind, namespace, case)
