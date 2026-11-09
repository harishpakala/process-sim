"""Created: 2026-10-31
Author: Harish"""

import unittest
from rdflib import Graph, Literal, URIRef, RDF
from process_sim.safsl.shacl.compiler import SELIRA
from process_sim.safsl.shacl.lifted_sc01 import AI, PC, evaluate_lifted_sc01

PROVENANCE = {
 "assetinventory": {"template_id": "https://example.org/sm/asset-inventory-template"},
 "productcatalog": {"template_id": "https://example.org/sm/product-catalog-template"},
}


class LiftedSC01Tests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.asset = URIRef("urn:asset:1")
        self.product = URIRef("urn:product:1")
        self.graph.add((self.asset, RDF.type, SELIRA.SC01Asset))
        self.graph.add((self.asset, AI.hasProductReference, Literal("P-1")))
        self.graph.add((self.product, PC.hasAssetIdentifier, Literal("P-1")))

    def evaluate(self, **kwargs):
        return evaluate_lifted_sc01(graph=self.graph, provenance=PROVENANCE,
                                   evidence_complete=True, identity_normalized=True,
                                   **kwargs)["verdict"]

    def test_valid_literal_match(self):
        self.assertEqual(self.evaluate(), "V")

    def test_missing_product(self):
        self.graph.remove((self.product, PC.hasAssetIdentifier, None))
        self.assertEqual(self.evaluate(), "F")

    def test_duplicate_product(self):
        self.graph.add((URIRef("urn:product:2"), PC.hasAssetIdentifier, Literal("P-1")))
        self.assertEqual(self.evaluate(), "F")

    def test_missing_reference_is_invalid(self):
        self.graph.remove((self.asset, AI.hasProductReference, None))
        self.assertEqual(self.evaluate(), "F")

    def test_unknown_without_attestation(self):
        self.assertEqual(evaluate_lifted_sc01(graph=self.graph, provenance=PROVENANCE)["verdict"], "U")

    def test_not_applicable_without_focus(self):
        self.graph.remove((self.asset, RDF.type, SELIRA.SC01Asset))
        self.assertEqual(self.evaluate(), "NA")


if __name__ == "__main__":
    unittest.main()
