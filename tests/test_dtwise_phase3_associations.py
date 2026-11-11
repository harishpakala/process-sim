"""Phase 3 offline regression: supported source filters and preserved phase 2 contract."""
import sys
import unittest
from pathlib import Path
from rdflib.plugins.sparql.parser import parseQuery
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from dtwise_phase3_associations import parse_question,compile_query
from dtwise_path_selector import load_catalog
from ebom_v2_nl2sparql import parse_intent
from dtwise_traversal_compiler import compile_query as compile_phase2

Q="Which {kind} are functionally associated with condenser C-001?"
class Phase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.catalog=load_catalog()
    def test_all(self):
        p=parse_question(Q.format(kind="engineering items"))
        self.assertEqual(p["intent"],"all_functional_associations")
        q=compile_query(p,self.catalog)
        self.assertNotIn('hasSourceDomain "DEXPI"',q)
        parseQuery(q)
    def test_ecad(self):
        p=parse_question(Q.format(kind="ECAD devices"))
        q=compile_query(p,self.catalog)
        self.assertIn('hasSourceDomain "ECAD"',q)
        self.assertIn('hasSourceGroup "Devices"',q)
    def test_actuating(self):
        p=parse_question(Q.format(kind="DEXPI actuating functions"))
        q=compile_query(p,self.catalog)
        self.assertIn('hasSourceGroup "ActuatingFunctions"',q)
    def test_instrumentation(self):
        p=parse_question(Q.format(kind="DEXPI instrumentation functions"))
        q=compile_query(p,self.catalog)
        self.assertIn('hasSourceGroup "InstrumentationFunctions"',q)
    def test_physical_membership_rejected(self):
        with self.assertRaises(ValueError):
            parse_question("Which ECAD devices are physically installed in condenser C-001?")
    def test_ambiguous_filters_rejected(self):
        with self.assertRaises(ValueError):
            parse_question(Q.format(kind="ECAD DEXPI devices"))
    def test_phase2_contract_unchanged(self):
        p=parse_intent("Which DEXPI instrumentation functions are functionally associated with reactor R-001? Return their engineering identifiers, descriptions, and asset identifiers.")
        q=compile_phase2(p,self.catalog)
        self.assertIn("?assetIdentifier",q)
        parseQuery(q)
if __name__=="__main__": unittest.main()
