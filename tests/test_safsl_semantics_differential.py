"""Bounded exhaustive differential checks: independent oracle vs compiled SHACL.

No oracle code calls the compiler or SPARQL engine. The SHACL side uses
the public compiler API and the production pySHACL execution path.
"""
import base64
import itertools
import unittest

from rdflib import Graph, Literal, RDF, URIRef
from pyshacl import validate

from process_sim.safsl.shacl.compiler import compile_contract
from process_sim.safsl.shacl.reference_semantics import Scope, evaluate_sc01

ASSET_CLASS = URIRef("urn:test:Asset")
PRODUCT_CLASS = URIRef("urn:test:Product")
REF = URIRef("urn:test:ref")
IDENTIFIER = URIRef("urn:test:identifier")


def encoded(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


SOURCE = """Specification Differential {
 Ref SubmodelTemplate assets = "%s";
 Ref SubmodelTemplate products = "%s";
 Contract SC_01 {
  forall a in assets {
   existsExactlyOne p in products where matches(a.ref, p.identifier);
  }
 }
}""" % (encoded("urn:template:assets"), encoded("urn:template:products"))

BINDINGS = {"templates": {
    "urn:template:assets": {"class": str(ASSET_CLASS),
                            "fields": {"ref": str(REF)}},
    "urn:template:products": {"class": str(PRODUCT_CLASS),
                              "fields": {"identifier": str(IDENTIFIER)},
                              "lexical_match": True},
}}


class CompilerDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ttl, cls.manifest = compile_contract(SOURCE, BINDINGS)
        cls.shapes = Graph().parse(data=ttl, format="turtle")

    def test_bounded_exhaustive_cardinality_semantics(self):
        # Two focus entities and two canonical products; each has either
        # no field value, A, or B. This exercises 3**4 = 81 snapshots.
        cases = 0
        for choices in itertools.product((None, "A", "B"), repeat=4):
            assets = {"a0": set(), "a1": set()}
            products = {"p0": set(), "p1": set()}
            graph = Graph()
            for index, key in enumerate(assets):
                subject = URIRef("urn:test:" + key)
                graph.add((subject, RDF.type, ASSET_CLASS))
                if choices[index] is not None:
                    assets[key].add(choices[index])
                    graph.add((subject, REF, Literal(choices[index])))
            for index, key in enumerate(products):
                subject = URIRef("urn:test:" + key)
                graph.add((subject, RDF.type, PRODUCT_CLASS))
                if choices[index + 2] is not None:
                    products[key].add(choices[index + 2])
                    graph.add((subject, IDENTIFIER, Literal(choices[index + 2])))
            expected, counts = evaluate_sc01(
                assets, products,
                Scope(frozenset(assets), complete=True,
                      identity_normalized=True, applicability_confirmed=True))
            conforms, _, report = validate(
                data_graph=graph, shacl_graph=self.shapes,
                inference="none", advanced=False)
            actual = "V" if conforms else "F"
            self.assertEqual(actual, expected, (choices, counts, report))
            cases += 1
        self.assertEqual(cases, 81)

    def test_reference_semantics_unknown_and_not_applicable(self):
        assets = {"a": {"A"}}
        products = {"p": {"A"}}
        self.assertEqual(evaluate_sc01(assets, products, Scope(frozenset({"a"})))[0], "U")
        self.assertEqual(evaluate_sc01(
            assets, products,
            Scope(frozenset(), True, True, True))[0], "NA")
        self.assertEqual(evaluate_sc01(
            assets, products,
            Scope(frozenset({"missing"}), True, True, True))[0], "U")

    def test_duplicate_canonical_entities_are_not_one(self):
        result, counts = evaluate_sc01(
            {"a": {"A"}}, {"p1": {"A"}, "p2": {"A"}},
            Scope(frozenset({"a"}), True, True, True))
        self.assertEqual(result, "F")
        self.assertEqual(counts["a"], 2)


if __name__ == "__main__":
    unittest.main()
