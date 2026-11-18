"""B27 filtered three-spoke hub join regression tests."""
import unittest
from unittest.mock import patch
from tests.test_dtwise_experimental_hub_join import ExplicitHubJoinTests
from process_sim.dtwise.experimental_multihop_cli import _plan_explicit_hub_join

QUESTION = ("Join DEXPI InstrumentationFunction, ECAD Device, and "
            "OPCUAConnectivity SignalMapping through AssetInventory Asset "
            "using AssetIdentifier where AssetIdentifier is https://aas.example.com/VC101.")

class FilteredHubJoinTests(unittest.TestCase):
    def setUp(self):
        fixture = ExplicitHubJoinTests()
        fixture.setUp()
        self.catalog = fixture.catalog
        self.leaves = fixture.leaves[:3]
        self.mappings = fixture.mappings[:3]

    def plan(self, mappings=None, question=QUESTION):
        with patch("process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan), patch(
                       "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            return _plan_explicit_hub_join(
                question, self.catalog,
                self.mappings if mappings is None else mappings,
                self.leaves, {x[0] for x in self.leaves} | {"assetinventory"}, {})

    def test_three_spoke_join_with_hub_filter(self):
        plan, selection = self.plan()
        self.assertEqual(len(plan["entities"]), 4)
        self.assertEqual(len(plan["edges"]), 3)
        self.assertEqual(plan["filters"], {
            "op": "eq", "entity": "n0",
            "predicate": "https://example.org/assetinventory/hasAssetIdentifier",
            "value": "https://aas.example.com/VC101"})
        self.assertEqual(selection["choice"], "VERIFIED_HUB_JOIN")
        self.assertTrue(plan["return_entities"])

    def test_b28_projects_opcua_node_id(self):
        predicate = "https://example.org/opcuaconnectivity/hasOPCUANodeId"
        target = next(e for e in self.catalog["entities"]
                      if e["domain"] == "opcuaconnectivity")
        target["properties"].append(predicate)
        question = QUESTION[:-1] + ", return OPCUAConnectivity SignalMapping OPCUANodeId."
        plan, selection = self.plan(question=question)
        self.assertEqual(len(plan["edges"]), 3)
        self.assertEqual(plan["filters"]["value"], "https://aas.example.com/VC101")
        self.assertEqual(plan["projections"], [
            {"entity": "n3", "predicate": predicate, "as": "value_0"}])
        self.assertFalse(plan["return_entities"])
        self.assertEqual(selection["choice"], "VERIFIED_HUB_JOIN")

    def test_b28_rejects_non_owned_projection(self):
        question = QUESTION[:-1] + ", return OPCUAConnectivity SignalMapping NotAProperty."
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.plan(question=question)

    def test_b28_rejects_non_member_projection_target(self):
        question = QUESTION[:-1] + ", return ProductCatalog Product ProductIdentifier."
        with self.assertRaisesRegex(ValueError, "target is missing or ambiguous"):
            self.plan(question=question)

    def test_b29_projects_ecad_and_opcua_properties(self):
        node_id = "https://example.org/opcuaconnectivity/hasOPCUANodeId"
        target = next(e for e in self.catalog["entities"]
                      if e["domain"] == "opcuaconnectivity")
        target["properties"].append(node_id)
        question = (QUESTION[:-1] +
                    ", return ECAD Device AssetIdentifier and "
                    "OPCUAConnectivity SignalMapping OPCUANodeId.")
        plan, selection = self.plan(question=question)
        self.assertEqual(len(plan["edges"]), 3)
        self.assertEqual(plan["filters"]["value"], "https://aas.example.com/VC101")
        self.assertEqual(plan["projections"], [
            {"entity": "n2", "predicate": "https://example.org/ecad/hasAssetIdentifier",
             "as": "value_0"},
            {"entity": "n3", "predicate": node_id, "as": "value_1"}])
        self.assertFalse(plan["return_entities"])
        self.assertEqual(selection["choice"], "VERIFIED_HUB_JOIN")

    def test_b29_rejects_unknown_second_property(self):
        question = (QUESTION[:-1] +
                    ", return ECAD Device AssetIdentifier and "
                    "OPCUAConnectivity SignalMapping UnknownProperty.")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.plan(question=question)

    def test_b29_rejects_duplicate_projection(self):
        question = (QUESTION[:-1] +
                    ", return ECAD Device AssetIdentifier and "
                    "ECAD Device AssetIdentifier.")
        with self.assertRaisesRegex(ValueError, "Duplicate hub projection"):
            self.plan(question=question)

    def test_b29_rejects_unqualified_second_projection(self):
        question = (QUESTION[:-1] +
                    ", return ECAD Device AssetIdentifier and OPCUANodeId.")
        with self.assertRaisesRegex(ValueError, "Invalid qualified hub projection"):
            self.plan(question=question)

    def test_unverified_spoke_rejected(self):
        mappings = [dict(m) for m in self.mappings]
        mappings[0]["verified"] = False
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings)

    def test_b33_ambiguous_verified_mapping_rejected(self):
        mappings = [dict(m) for m in self.mappings]
        duplicate = dict(mappings[0])
        duplicate["id"] = mappings[0]["id"] + "-competing"
        duplicate["evidence_ids"] = ["independent-evidence-b33"]
        mappings.append(duplicate)
        self.assertTrue(all(m["verified"] for m in mappings))
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings=mappings)

    def test_b34_verified_mapping_without_evidence_rejected(self):
        mappings = [dict(m) for m in self.mappings]
        mappings[0]["verified"] = True
        mappings[0]["evidence_ids"] = []
        self.assertTrue(mappings[0]["verified"])
        self.assertEqual(mappings[0]["evidence_ids"], [])
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings=mappings)

    def test_b35_mapping_with_non_owned_predicate_rejected(self):
        mappings = [dict(m) for m in self.mappings]
        ecad_mapping = next(m for m in mappings if m["right_domain"] == "ecad")
        ecad_mapping["right_property"] = (
            "https://example.org/ecad/hasUndeclaredAssetIdentifier")
        self.assertTrue(ecad_mapping["verified"])
        self.assertTrue(ecad_mapping["evidence_ids"])
        ecad_shape = next(e for e in self.catalog["entities"]
                          if e["domain"] == "ecad")
        self.assertNotIn(ecad_mapping["right_property"], ecad_shape["properties"])
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings=mappings)

    def test_b36_wrong_domain_predicate_rejected(self):
        mappings = [dict(m) for m in self.mappings]
        ecad_mapping = next(m for m in mappings if m["right_domain"] == "ecad")
        dexpi_shape = next(e for e in self.catalog["entities"]
                           if e["domain"] == "dexpi")
        ecad_shape = next(e for e in self.catalog["entities"]
                          if e["domain"] == "ecad")
        wrong_domain_predicate = "https://example.org/dexpi/hasAssetIdentifier"
        self.assertIn(wrong_domain_predicate, dexpi_shape["properties"])
        self.assertNotIn(wrong_domain_predicate, ecad_shape["properties"])
        ecad_mapping["right_property"] = wrong_domain_predicate
        self.assertTrue(ecad_mapping["verified"])
        self.assertTrue(ecad_mapping["evidence_ids"])
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping"):
            self.plan(mappings=mappings)

    def test_unrequested_filter_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "Hub filter must use"):
            self.plan(question=QUESTION.replace(
                "where AssetIdentifier is", "where ProductIdentifier is"))

if __name__ == "__main__":
    unittest.main()
