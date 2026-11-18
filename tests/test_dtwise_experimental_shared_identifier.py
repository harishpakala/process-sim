"""Offline regression tests for B25 shared identifier projections."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import _plan_shared_identifier_values

QUESTION = ("List AssetIdentifier values shared by DEXPI InstrumentationFunction "
            "and OPCUAConnectivity SignalMapping.")


class SharedIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.start = ("dexpi", "urn:InstrumentationFunction")
        self.end = ("opcuaconnectivity", "urn:SignalMapping")
        self.left = "https://example.org/dexpi/hasAssetIdentifier"
        self.right = "https://example.org/opcuaconnectivity/hasAssetIdentifier"
        self.catalog = {
            "entities": [
                {"domain": "dexpi", "shape": self.start[1],
                 "display_name": "InstrumentationFunction",
                 "properties": [self.left]},
                {"domain": "opcuaconnectivity", "shape": self.end[1],
                 "display_name": "SignalMapping", "properties": [self.right]},
            ],
            "shacl_edges": [],
        }
        self.mappings = [{
            "id": "dexpi-opcua-asset-identifier", "verified": True,
            "evidence_ids": ["e1"], "left_domain": "dexpi",
            "right_domain": "opcuaconnectivity",
            "left_property": self.left, "right_property": self.right,
        }]

    def plan(self, mappings=None):
        with patch(
            "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
            side_effect=lambda plan, index, mappings: plan,
        ), patch(
            "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage",
        ):
            return _plan_shared_identifier_values(
                QUESTION, self.catalog,
                self.mappings if mappings is None else mappings,
                [self.start, self.end], {"dexpi", "opcuaconnectivity"}, {},
            )

    def test_projects_verified_shared_identifier(self):
        plan, selection = self.plan()
        self.assertEqual(len(plan["edges"]), 1)
        self.assertEqual(plan["edges"][0]["mapping_id"],
                         "dexpi-opcua-asset-identifier")
        self.assertEqual(plan["projections"], [
            {"entity": "n0", "predicate": self.left, "as": "shared_identifier"}])
        self.assertEqual(selection["choice"], "VERIFIED_SHARED_IDENTIFIER")

    def test_unverified_mapping_rejected(self):
        mappings = [dict(self.mappings[0], verified=False)]
        with self.assertRaisesRegex(ValueError, "no unique verified direct mapping"):
            self.plan(mappings)

    def test_ambiguous_mapping_rejected(self):
        mappings = self.mappings + [dict(self.mappings[0], id="duplicate")]
        with self.assertRaisesRegex(ValueError, "no unique verified direct mapping"):
            self.plan(mappings)


if __name__ == "__main__":
    unittest.main()
