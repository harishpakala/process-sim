"""SC-01 compiler tests: run with python -m unittest tests/test_safsl_shacl_sc01.py."""

# Created: 2026-10-31
# Author: Harish
import base64
import unittest

from rdflib import Graph, Namespace, RDF
from pyshacl import validate

from process_sim.safsl.shacl.compiler import CompilationError, compile_contract

EX = Namespace("https://example.org/selira/")
A = "urn:example:aas:template:AssetInventory"
P = "urn:example:aas:template:ProductCatalog"
enc = lambda s: base64.b64encode(s.encode()).decode()
SOURCE = f"""Specification AssetProductIntegrity {{
 Ref SubmodelTemplate assets = "{enc(A)}";
 Ref SubmodelTemplate products = "{enc(P)}";
 Contract SC_01 {{
   forall asset in assets {{
     existsExactlyOne product in products
       where matches(asset.productRef, product.canonicalId);
   }}
 }}
}}"""
BINDINGS = {"templates": {
 A: {"class": str(EX.Asset), "fields": {"productRef": str(EX.productRef)}, "complete": True},
 P: {"class": str(EX.CanonicalProduct), "fields": {"canonicalId": str(EX.canonicalId)}, "complete": True},
}}


def evaluate(products, asset_ref="P1"):
    ttl, manifest = compile_contract(SOURCE, BINDINGS)
    data = Graph()
    asset = EX.asset1
    data.add((asset, RDF.type, EX.Asset))
    if asset_ref is not None:
        data.add((asset, EX.productRef, EX[asset_ref]))
    for product, canonical_id in products:
        data.add((EX[product], RDF.type, EX.CanonicalProduct))
        data.add((EX[product], EX.canonicalId, EX[canonical_id]))
    conforms, _, _ = validate(data_graph=data, shacl_graph=Graph().parse(data=ttl, format="turtle"),
                               inference="none", advanced=False)
    return conforms, manifest


class TestSC01(unittest.TestCase):
    def test_exactly_one(self):
        self.assertTrue(evaluate([("p1", "P1")])[0])

    def test_zero_matches(self):
        self.assertFalse(evaluate([])[0])

    def test_two_distinct_canonical_products(self):
        self.assertFalse(evaluate([("p1", "P1"), ("p2", "P1")])[0])

    def test_multiple_descriptions_same_entity(self):
        self.assertTrue(evaluate([("p1", "P1"), ("p1", "P1")])[0])

    def test_missing_reference(self):
        self.assertFalse(evaluate([("p1", "P1")], asset_ref=None)[0])

    def test_dependencies_include_both_templates(self):
        self.assertEqual(set(evaluate([("p1", "P1")])[1]["contracts"][0]["dependencies"]), {A, P})

    def test_reject_missing_binding(self):
        with self.assertRaises(CompilationError):
            compile_contract(SOURCE, {"templates": {}})

    def test_reject_malformed_base64(self):
        with self.assertRaises(CompilationError):
            compile_contract(SOURCE.replace(enc(A), "%%%"), BINDINGS)


if __name__ == "__main__":
    unittest.main()
