"""Regression checks for additive EBOM V2 overlay; run python -m unittest discover -s tests -p 'test_ebom_v2_traversal.py'."""
import json
import sys
import unittest
from pathlib import Path
from rdflib import RDF
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from build_ebom_v2_graph import build, CORE, EBOM, uri

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "semantic/instances/tep/tep_engineering_bom_instance.json"
EXPECTED = {"FI_106", "TI_101", "TI_104", "LI_101", "PI_101"}

class TestEBOMV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build(json.loads(INPUT.read_text(encoding="utf-8")))

    def test_reactor_grounding_and_functional_path(self):
        g = self.graph
        reactor = next(s for s in g.subjects(EBOM.hasEngineeringLocalId, None)
                       if (s, EBOM.hasEngineeringLocalId, None) in g
                       and any(str(v) == "R-001" for v in g.objects(s, EBOM.hasEngineeringLocalId)))
        assembly = uri("assembly", "ASM-REACTOR")
        self.assertIn((reactor, CORE.hasRecordedParent, assembly), g)
        found = set()
        for association in g.subjects(RDF.type, CORE.FunctionalAssociation):
            if (association, CORE.functionalAssociationTarget, assembly) not in g:
                continue
            for item in g.objects(association, CORE.functionalAssociationSource):
                if any(str(v) == "DEXPI" for v in g.objects(item, EBOM.hasSourceDomain)) and any(
                    str(v) == "InstrumentationFunctions" for v in g.objects(item, EBOM.hasSourceGroup)):
                    found.update(str(v) for v in g.objects(item, EBOM.hasEngineeringLocalId))
        self.assertEqual(found, EXPECTED)

    def test_no_physical_bom_occurrence_assertions(self):
        g = self.graph
        self.assertEqual(len(list(g.subjects(RDF.type, CORE.BOMOccurrence))), 0)
        self.assertEqual(len(list(g.triples((None, CORE.hasBOMOccurrence, None)))), 0)

    def test_all_functional_associations_have_evidence(self):
        g = self.graph
        for a in g.subjects(RDF.type, CORE.FunctionalAssociation):
            self.assertTrue(list(g.objects(a, CORE.associationBasis)))
            self.assertTrue(list(g.objects(a, CORE.sourceRecordId)))

if __name__ == "__main__":
    unittest.main()
