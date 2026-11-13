"""Deterministic EBOM V2 NL compiler tests (offline)."""
import sys
import unittest
from pathlib import Path
from rdflib.plugins.sparql.parser import parseQuery
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from ebom_v2_nl2sparql import parse_intent, compile_sparql

Q = ("Which DEXPI instrumentation functions are functionally associated with reactor R-001? "
     "Return their engineering identifiers, descriptions, and asset identifiers.")

class TestEBOMV2Compiler(unittest.TestCase):
    def test_reactor_query_compiles(self):
        plan = parse_intent(Q)
        self.assertEqual(plan["equipment_tag"], "R-001")
        query = compile_sparql(plan)
        parseQuery(query)
        self.assertIn("core:functionalAssociationTarget ?assembly", query)
        self.assertIn('ebom:hasEngineeringLocalId "R-001"', query)

    def test_other_equipment_tag_without_hardcoded_mapping(self):
        q = Q.replace("reactor R-001", "condenser C-001")
        plan = parse_intent(q)
        self.assertEqual(plan["equipment_tag"], "C-001")
        parseQuery(compile_sparql(plan))

    def test_rejects_physical_membership(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_RELATION"):
            parse_intent(Q + " Are they physically installed?")

    def test_rejects_unrelated_domain(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_DOMAIN"):
            parse_intent(Q + " Include OPC UA.")

    def test_rejects_ambiguous_tags(self):
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_ENTITY"):
            parse_intent(Q + " Also C-001.")

    def test_rejects_extra_output(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_TERMS"):
            parse_intent(Q + " Include serial numbers.")

if __name__ == "__main__":
    unittest.main()
