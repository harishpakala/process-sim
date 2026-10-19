"""Regression checks for AAS-first semantic reference lifting.

Run: python -m unittest discover -s tests -p test_semantic_reference_lifting.py
"""
import unittest
from types import SimpleNamespace
from rdflib import Graph, Literal, URIRef
from semantic.ontoutils import compute_uri, lift_semantic_id, make_literal, semanticDict


def reference(value):
    return SimpleNamespace(keys=[SimpleNamespace(value=value)])


class SemanticReferenceLiftingTests(unittest.TestCase):
    def test_unverified_eclass_irdi_is_preserved_not_classified(self):
        element = SimpleNamespace(
            semantic_id=reference("0173-1#02-UNVERIFIED"),
            supplemental_semantic_ids=[],
        )
        graph = Graph()
        subject = compute_uri("urn:test:asset", "Assets.Asset1.TechnicalProperty")
        lift_semantic_id(graph, "urn:test:asset", element, "Assets.Asset1.TechnicalProperty")
        self.assertIn((subject, semanticDict["AAS"]["semanticId"],
                       Literal("0173-1#02-UNVERIFIED")), graph)
        self.assertNotIn((subject, semanticDict["AAS"]["classificationReference"], None), graph)

    def test_qudt_references_are_preserved_separately(self):
        unit = "http://qudt.org/vocab/unit/KiloPA"
        quantity = "http://qudt.org/vocab/quantitykind/Pressure"
        element = SimpleNamespace(
            semantic_id=reference(unit),
            supplemental_semantic_ids=[reference(quantity)],
        )
        graph = Graph()
        subject = compute_uri("urn:test", "Measurement")
        lift_semantic_id(graph, "urn:test", element, "Measurement")
        self.assertIn((subject, semanticDict["QUDT"]["unit"], URIRef(unit)), graph)
        self.assertIn((subject, semanticDict["AAS"]["supplementalSemanticId"],
                       Literal(quantity)), graph)
        # Supplemental reference is not silently promoted to a primary quantity assertion.
        self.assertNotIn((subject, semanticDict["QUDT"]["hasQuantityKind"], URIRef(quantity)), graph)

    def test_typed_literals_and_absent_values(self):
        self.assertIsNone(make_literal(None, "xs:double"))
        self.assertEqual(make_literal("2.5", "xs:double").toPython(), 2.5)


if __name__ == "__main__":
    unittest.main()
