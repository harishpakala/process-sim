"""Regression checks for AAS-to-RDF semantic lifting.

Run: python3 -m unittest discover -s tests -p 'test_semantic_contract.py'
Requires the project's semantic lifting dependencies.
"""
import json
from pathlib import Path
import unittest

from rdflib import RDF, URIRef, Literal
import aas_core3_1.jsonization as aas_jsonization

from semantic.instance_lifting import build_instance_graph
from semantic.ontoutils import compute_uri, semanticDict

ROOT = Path(__file__).resolve().parents[1]

class SemanticContractTests(unittest.TestCase):
    def test_product_smc_and_technical_properties(self):
        source = json.loads((ROOT / "examples/aas/product_catalog_instance.json").read_text(encoding="utf-8"))
        model = aas_jsonization.submodel_from_jsonable(source)
        graph = build_instance_graph(model, "productcatalog", "https://example.org/sm/product-catalog-template")
        ns = semanticDict["PRODUCTCATALOG"]
        product = compute_uri(model.id, "Products.SMC_PFMV505_1")
        technical = compute_uri(model.id, "Products.SMC_PFMV505_1.TechnicalProperties")
        self.assertIn((product, ns["hasTechnicalProperties"], technical), graph)
        self.assertIn((technical, RDF.type, semanticDict["AAS"]["SMC"]), graph)
        self.assertIn((product, ns["hasManufacturerPartNumber"], Literal("PFMV505-1")), graph)
        self.assertIn((technical, ns["hasRatedFlowRange"], Literal("0 to 0.5 L/min")), graph)
        self.assertNotIn((product, ns["hasRatedFlowRange"], Literal("0 to 0.5 L/min")), graph)

    def test_ecad_instance_is_liftable(self):
        source = json.loads((ROOT / "examples/aas/tep_ecad_instance.json").read_text(encoding="utf-8"))
        model = aas_jsonization.submodel_from_jsonable(source)
        graph = build_instance_graph(model, "ecad", "https://example.org/sm/ecad")
        self.assertIn((compute_uri(model.id, ""), RDF.type, semanticDict["AAS"]["Submodel"]), graph)
        self.assertGreater(len(graph), 0)

if __name__ == "__main__":
    unittest.main()
