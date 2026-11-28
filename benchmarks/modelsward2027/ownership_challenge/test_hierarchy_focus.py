"""Hierarchy focusing regression tests (synthetic shape registry)."""
import unittest
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import (
    _hierarchical_property_matches, _maximal_shape_hits)

class HierarchyTests(unittest.TestCase):
    shapes = {k: {"labels":[v]} for k,v in
              [("d","Device"),("s","Symbol"),("de","EndPoint"),("se","EndPoint"),
               ("dp","PLCEndPoint")]}
    candidates = [{"id":str(i)} for i in range(4)]
    registry = {str(i):{"node_uris":p} for i,p in enumerate(
        [["root","d"],["root","d","de"],["root","s","se"],["root","d","dp"]])}

    def resolve(self, question):
        hits = _maximal_shape_hits(question,self.shapes)
        candidates = [c for c in self.candidates
                      if self.registry[c["id"]]["node_uris"][-1] in hits]
        return [c["id"] for c in _hierarchical_property_matches(
            question,candidates,self.registry,self.shapes,hits)]

    def test_device_endpoint(self):
        self.assertEqual(self.resolve("Show LocalId values of Device EndPoint entities"),["1"])

    def test_symbol_endpoint(self):
        self.assertEqual(self.resolve("Show LocalId values of Symbol EndPoint entities"),["2"])

    def test_plc(self):
        self.assertEqual(self.resolve("Show Address values of Device PLCEndPoint entities"),["3"])

    def test_ambiguous(self):
        self.assertEqual(self.resolve("Show LocalId values of EndPoint entities"),["1","2"])

    def test_coordination(self):
        self.assertEqual(self.resolve("Show LocalId values of Device and EndPoint entities"),["0","1","2"])

if __name__ == "__main__":
    unittest.main()
