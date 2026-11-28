"""Regression tests for overlapping schema concept mentions."""
import unittest
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import _maximal_shape_hits

class ConceptMatchingTests(unittest.TestCase):
    shapes = {"e": {"labels": ["EndPoint"]}, "p": {"labels": ["PLCEndPoint"]},
              "p2": {"labels": ["PLCEndPoint"]}, "d": {"labels": ["Device"]}}

    def test_nested_name(self):
        self.assertEqual(_maximal_shape_hits("Device PLCEndPoint", self.shapes), {"d","p","p2"})

    def test_separate_mentions(self):
        self.assertEqual(_maximal_shape_hits("PLCEndPoint and EndPoint", self.shapes), {"e","p","p2"})

    def test_plural(self):
        self.assertEqual(_maximal_shape_hits("Devices and EndPoints", self.shapes), {"d","e"})

    def test_spaced_case(self):
        self.assertEqual(_maximal_shape_hits("plc end point", self.shapes), {"p","p2"})

if __name__ == "__main__":
    unittest.main()
