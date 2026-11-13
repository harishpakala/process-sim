"""Offline catalog/path/identity/compilation regression tests for EBOM V2."""
import json
import sys
import unittest
from pathlib import Path
from rdflib import Graph
from rdflib.plugins.sparql.parser import parseQuery

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from dtwise_entity_resolver import resolve_local
from dtwise_path_selector import load_catalog, select_path
from dtwise_traversal_compiler import compile_query
from ebom_v2_nl2sparql import parse_intent

QUESTION = ("Which DEXPI instrumentation functions are functionally associated with "
            "reactor R-001? Return their engineering identifiers, descriptions, and asset identifiers.")

class TestDTWiSETraversal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.graph = Graph().parse(ROOT / "semantic/derived/tep_ebom_v2.ttl", format="turtle")

    def test_catalog_path(self):
        path = select_path(self.catalog, "dexpi_instrumentation_functional_association")
        self.assertEqual([e["id"] for e in path],
                         ["recorded_parent", "association_target", "association_source"])

    def test_resolve_reactor(self):
        result = resolve_local(self.graph, "R-001")
        self.assertTrue(result["equipment_uri"].endswith("/item/EBOM-0001"))
        self.assertTrue(result["assembly_uri"].endswith("/assembly/ASM-REACTOR"))

    def test_resolve_other_equipment(self):
        result = resolve_local(self.graph, "C-001")
        self.assertTrue(result["assembly_uri"].endswith("/assembly/ASM-CONDENSER"))

    def test_fail_closed_unknown_tag(self):
        with self.assertRaisesRegex(ValueError, "ENTITY_NOT_FOUND"):
            resolve_local(self.graph, "ZZ-999999")

    def test_compile_resolved_reactor(self):
        plan = parse_intent(QUESTION)
        resolution = resolve_local(self.graph, "R-001")
        query = compile_query(plan, self.catalog, resolution)
        parseQuery(query)
        self.assertIn("VALUES ?equipment", query)
        self.assertIn("core:functionalAssociationTarget ?assembly", query)
        self.assertIn("core:hasRecordedParent ?assembly", query)

    def test_compile_resolved_condenser(self):
        plan = parse_intent(QUESTION.replace("reactor R-001", "condenser C-001"))
        query = compile_query(plan, self.catalog, resolve_local(self.graph, "C-001"))
        parseQuery(query)
        self.assertIn('ebom:hasEngineeringLocalId "C-001"', query)

    def test_no_physical_edges_in_catalog(self):
        self.assertFalse(self.catalog["constraints"]["physical_membership_inferred"])
        self.assertFalse(any(e["semantics"] == "physical_membership"
                             for e in self.catalog["edges"]))

    def test_unsupported_intent(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_INTENT"):
            select_path(self.catalog, "physical_membership")

if __name__ == "__main__":
    unittest.main()
