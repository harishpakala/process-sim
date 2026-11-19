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

    def test_b37_missing_required_spoke_mapping_rejected(self):
        mappings = [dict(m) for m in self.mappings
                    if m["right_domain"] != "ecad"]
        self.assertEqual(len(mappings), len(self.mappings) - 1)
        self.assertFalse(any(m["right_domain"] == "ecad" for m in mappings))
        with self.assertRaisesRegex(ValueError, "No unique verified hub mapping for ecad"):
            self.plan(mappings=mappings)

    def test_b14_count_does_not_infer_property_target(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            plan_experimental_multihop,
        )
        catalog = {"entities": [
            {"domain": "opcuaconnectivity", "shape": "urn:SignalMapping",
             "display_name": "SignalMapping",
             "properties": ["https://example.org/opcuaconnectivity/hasAssetIdentifier"]},
            {"domain": "dexpi", "shape": "urn:InstrumentationFunction",
             "display_name": "InstrumentationFunction",
             "properties": ["https://example.org/dexpi/hasCount"]},
        ], "shacl_edges": []}
        question = "Count OPCUAConnectivity SignalMapping entities."
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=catalog), patch(
                       "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                       return_value=(catalog, set())), patch(
                       "process_sim.dtwise.experimental_evidence_selection.select_evidence_plan",
                       return_value=({"operation": {"type": "count"}}, {"choice": "TEST"})
                   ) as select, patch(
                       "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            plan, _ = plan_experimental_multihop(
                question, {}, [], model="unused", ollama_host="unused",
                timeout=1)
        self.assertEqual(plan["operation"]["type"], "count")
        paths = select.call_args.args[1]
        self.assertEqual(paths, [{"nodes": [("opcuaconnectivity", "urn:SignalMapping")],
                                  "steps": []}])

    def test_b19_filtered_single_shape_list(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            plan_experimental_multihop,
        )
        catalog = {"entities": [
            {"domain": "opcuaconnectivity", "shape": "urn:SignalMapping",
             "display_name": "SignalMapping",
             "properties": [
                 "https://example.org/opcuaconnectivity/hasAssetIdentifier",
                 "https://example.org/opcuaconnectivity/hasSignalName"]},
            {"domain": "other", "shape": "urn:Other",
             "display_name": "Other",
             "properties": ["https://example.org/other/hasAssetIdentifier"]},
        ], "shacl_edges": []}
        question = ("For OPCUAConnectivity SignalMapping entities where "
                    "AssetIdentifier is https://aas.example.com/FI103, list SignalName.")
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=catalog), patch(
                       "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                       return_value=(catalog, set())), patch(
                       "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                       side_effect=lambda plan, index, mappings: plan), patch(
                       "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            plan, selection = plan_experimental_multihop(
                question, {}, [], model="unused", ollama_host="unused",
                timeout=1)
        self.assertEqual(selection["choice"], "VERIFIED_SINGLE_SHAPE_LOOKUP")
        self.assertEqual(plan["operation"], {"type": "select"})
        self.assertEqual(plan["projections"], [{
            "entity": "n0",
            "predicate": "https://example.org/opcuaconnectivity/hasSignalName",
            "as": "value_0"}])
        self.assertEqual(plan["filters"], {
            "op": "eq", "entity": "n0",
            "predicate": "https://example.org/opcuaconnectivity/hasAssetIdentifier",
            "value": "https://aas.example.com/FI103"})

    def test_unrequested_filter_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "Hub filter must use"):
            self.plan(question=QUESTION.replace(
                "where AssetIdentifier is", "where ProductIdentifier is"))


    def test_experimental_selection_writes_diagnostics_on_timeout(self):
        import json
        import tempfile
        from pathlib import Path
        from process_sim.dtwise.experimental_evidence_selection import select_evidence_plan

        catalog = {"entities": [{
            "domain": "dexpi", "shape": "urn:InstrumentationFunction",
            "display_name": "InstrumentationFunction",
            "properties": ["urn:hasLocalId"],
        }]}
        paths = [{"nodes": [("dexpi", "urn:InstrumentationFunction")],
                  "steps": []}]
        with tempfile.TemporaryDirectory() as directory:
            diagnostic_path = Path(directory) / "b21-diagnostics.json"

            def timeout_request(url, payload, timeout):
                raise TimeoutError("timed out")

            with self.assertRaisesRegex(TimeoutError, "timed out"):
                select_evidence_plan(
                    "Get LocalId for DEXPI InstrumentationFunction.",
                    paths, catalog, {}, [], model="test",
                    request_json=timeout_request,
                    ollama_host="http://unused", timeout=60,
                    prompt_diagnostics={"path": str(diagnostic_path)})
            report = json.loads(diagnostic_path.read_text(encoding="utf-8"))
            self.assertEqual(report["stage"], "experimental_evidence_selection")
            self.assertEqual(report["candidate_path_count"], 1)
            self.assertEqual(report["candidate_property_count"], 1)
            self.assertGreater(report["payload_bytes"], 0)
            self.assertEqual(report["request_status"], "failed")
            self.assertEqual(report["request_error_type"], "TimeoutError")
            self.assertIn("request_wall_seconds", report)
            self.assertNotIn("path", report)

if __name__ == "__main__":
    unittest.main()
