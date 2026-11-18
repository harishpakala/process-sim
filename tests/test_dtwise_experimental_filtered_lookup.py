"""B26 filtered cross-domain lookup regression tests."""
import unittest
from unittest.mock import patch
from process_sim.dtwise.experimental_multihop_cli import _plan_filtered_cross_domain_lookup

Q = ("Get OPCUAConnectivity SignalMapping OPCUANodeId for DEXPI "
     "InstrumentationFunction where AssetIdentifier is https://aas.example.com/VC101.")

class FilteredLookupTests(unittest.TestCase):
    def setUp(self):
        self.source = ("dexpi", "urn:dexpi")
        self.target = ("opcuaconnectivity", "urn:opcua")
        self.key0 = "https://example.org/dexpi/hasAssetIdentifier"
        self.key1 = "https://example.org/opcuaconnectivity/hasAssetIdentifier"
        self.output = "https://example.org/opcuaconnectivity/hasOPCUANodeId"
        self.catalog = {"entities": [
            {"domain": "dexpi", "shape": self.source[1],
             "display_name": "InstrumentationFunction", "properties": [self.key0]},
            {"domain": "opcuaconnectivity", "shape": self.target[1],
             "display_name": "SignalMapping", "properties": [self.key1, self.output]}],
            "shacl_edges": []}
        self.mappings = [{"id": "dexpi-opcua-asset-identifier", "verified": True,
                          "evidence_ids": ["e1"], "left_domain": "dexpi",
                          "right_domain": "opcuaconnectivity",
                          "left_property": self.key0, "right_property": self.key1}]

    def plan(self, mappings=None):
        with patch("process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan), patch(
                       "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            return _plan_filtered_cross_domain_lookup(
                Q, self.catalog, self.mappings if mappings is None else mappings,
                [self.source, self.target], {"dexpi", "opcuaconnectivity"}, {})

    def test_verified_filter_and_projection(self):
        plan, selection = self.plan()
        self.assertEqual(selection["choice"], "VERIFIED_FILTERED_LOOKUP")
        self.assertEqual(plan["projections"], [
            {"entity": "n1", "predicate": self.output, "as": "value_0"}])
        self.assertEqual(plan["filters"], {
            "op": "eq", "entity": "n0", "predicate": self.key0,
            "value": "https://aas.example.com/VC101"})
        self.assertEqual(len(plan["edges"]), 1)

    def test_unverified_mapping_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no unique verified direct mapping"):
            self.plan([dict(self.mappings[0], verified=False)])

    def test_ambiguous_mapping_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no unique verified direct mapping"):
            self.plan(self.mappings + [dict(self.mappings[0], id="duplicate")])

if __name__ == "__main__":
    unittest.main()
