"""Offline tests for the explicit evidence-verified branching hub join."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import (
    _plan_explicit_hub_join,
)

QUESTION = (
    "Join DEXPI InstrumentationFunction, ECAD Device, "
    "OPCUAConnectivity SignalMapping, and ProductCatalog Product "
    "through AssetInventory Asset using AssetIdentifier and ProductIdentifier."
)


class ExplicitHubJoinTests(unittest.TestCase):
    def setUp(self):
        self.hub = ("assetinventory", "urn:Asset")
        self.leaves = [
            ("dexpi", "urn:InstrumentationFunction"),
            ("ecad", "urn:Device"),
            ("opcuaconnectivity", "urn:SignalMapping"),
            ("productcatalog", "urn:Product"),
        ]
        self.catalog = {"entities": [], "shacl_edges": []}
        for domain, shape in [self.hub] + self.leaves:
            label = shape.rsplit(":", 1)[-1]
            keys = (["ProductIdentifier"] if domain == "productcatalog"
                    else ["AssetIdentifier", "ProductIdentifier"]
                    if domain == "assetinventory" else ["AssetIdentifier"])
            self.catalog["entities"].append({
                "domain": domain, "shape": shape, "display_name": label,
                "properties": [f"https://example.org/{domain}/has{key}" for key in keys],
            })
        self.mappings = []
        for domain, _ in self.leaves:
            key = ("ProductIdentifier" if domain == "productcatalog"
                   else "AssetIdentifier")
            self.mappings.append({
                "id": "assetinventory-" + domain + "-" + key,
                "verified": True, "evidence_ids": ["e1"],
                "left_domain": "assetinventory", "right_domain": domain,
                "left_property": "https://example.org/assetinventory/has" + key,
                "right_property": "https://example.org/" + domain + "/has" + key,
            })

    def plan(self, mappings=None):
        with patch(
            "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
            side_effect=lambda plan, index, mappings: plan,
        ), patch(
            "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage",
        ):
            return _plan_explicit_hub_join(
                QUESTION, self.catalog,
                self.mappings if mappings is None else mappings,
                self.leaves, set(x[0] for x in self.leaves) | {"assetinventory"},
                {},
            )

    def test_verified_star_has_four_edges_and_five_entities(self):
        plan, selection = self.plan()
        self.assertEqual(len(plan["entities"]), 5)
        self.assertEqual(len(plan["edges"]), 4)
        self.assertEqual(selection["choice"], "VERIFIED_HUB_JOIN")
        self.assertTrue(plan["return_entities"])
        self.assertEqual(plan["projections"], [])
        self.assertEqual(
            {e["mapping_id"] for e in plan["edges"]},
            {m["id"] for m in self.mappings},
        )

    def test_unverified_spoke_fails_closed(self):
        mappings = [dict(m) for m in self.mappings]
        mappings[0]["verified"] = False
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings)

    def test_missing_product_key_fails_closed(self):
        mappings = [dict(m) for m in self.mappings]
        mappings[-1]["left_property"] = "https://example.org/assetinventory/hasAssetIdentifier"
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings)


if __name__ == "__main__":
    unittest.main()
