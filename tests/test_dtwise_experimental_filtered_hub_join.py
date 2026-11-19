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


    def test_b21_prompt_keeps_requested_and_join_properties_only(self):
        import json
        from process_sim.dtwise.experimental_evidence_selection import select_evidence_plan

        question = ("Get OPCUAConnectivity SignalMapping SignalName for "
                    "DEXPI InstrumentationFunction with LocalId FI-001.")
        catalog = {"entities": [
            {"domain": "dexpi", "shape": "urn:InstrumentationFunction",
             "display_name": "InstrumentationFunction",
             "properties": ["urn:hasLocalId", "urn:hasJoinKey", "urn:hasUnused"]},
            {"domain": "opcuaconnectivity", "shape": "urn:SignalMapping",
             "display_name": "SignalMapping",
             "properties": ["urn:hasSignalName", "urn:hasJoinKey", "urn:hasUnused"]},
        ]}
        paths = [{"nodes": [
            ("dexpi", "urn:InstrumentationFunction"),
            ("opcuaconnectivity", "urn:SignalMapping")],
            "steps": [{"kind": "mapping", "mapping_id": "M1",
                       "left_predicate": "urn:hasJoinKey",
                       "right_predicate": "urn:hasJoinKey"}]}]
        observed = {}

        def capture_request(url, payload, timeout):
            observed["choices"] = json.loads(payload["messages"][1]["content"])["choices"]
            raise TimeoutError("stop before binding")

        with self.assertRaises(TimeoutError):
            select_evidence_plan(
                question, paths, catalog, {}, [], model="test",
                request_json=capture_request, ollama_host="http://unused",
                timeout=1)
        properties = observed["choices"][0]["properties"]
        labels = [item["label"] for item in properties]
        self.assertIn("SignalName", labels)
        self.assertIn("LocalId", labels)
        self.assertIn("JoinKey", labels)
        self.assertNotIn("Unused", labels)
        self.assertEqual(len(properties), 4)

    def test_unstructured_question_keeps_full_property_catalog(self):
        from process_sim.dtwise.experimental_evidence_selection import (
            _explicit_lookup_property_labels)
        self.assertIsNone(_explicit_lookup_property_labels(
            "List all SignalMapping attributes associated with instruments."))
        self.assertEqual(_explicit_lookup_property_labels(
            "Get OPCUAConnectivity SignalMapping SignalName for "
            "DEXPI InstrumentationFunction with LocalId FI-001."),
            {"signalname", "localid"})


class NamedDirectMappingLookupTests(unittest.TestCase):
    def setUp(self):
        self.question = ("Find OPCUAConnectivity SignalMapping SignalName associated "
                         "with DEXPI InstrumentationFunction through AssetIdentifier.")
        self.source = ("dexpi", "urn:dexpi")
        self.target = ("opcuaconnectivity", "urn:opcua")
        self.catalog = {"entities": [
            {"domain": "dexpi", "shape": "urn:dexpi",
             "display_name": "InstrumentationFunction",
             "properties": ["https://example.org/common/hasAssetIdentifier", "https://example.org/dexpi/hasLocalId"]},
            {"domain": "opcuaconnectivity", "shape": "urn:opcua",
             "display_name": "SignalMapping",
             "properties": ["https://example.org/common/hasAssetIdentifier", "https://example.org/opcuaconnectivity/hasSignalName"]},
        ]}
        self.path = {"nodes": [self.source, self.target],
                     "steps": [{"kind": "mapping", "mapping_id": "M1",
                                "left_predicate": "https://example.org/common/hasAssetIdentifier",
                                "right_predicate": "https://example.org/common/hasAssetIdentifier"}]}

    def run_plan(self, paths):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_direct_mapping_lookup)
        with patch("process_sim.dtwise.experimental_multihop_cli.enumerate_evidenced_paths",
                   return_value=paths), patch(
                   "process_sim.dtwise.experimental_multihop_cli.bind_evidenced_path",
                   return_value={"verified": True}) as bind, patch(
                   "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan), patch(
                   "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            result = _plan_named_direct_mapping_lookup(
                self.question, self.catalog, [], [self.source, self.target],
                {"dexpi", "opcuaconnectivity"}, {})
        return result, bind

    def test_b22_uses_named_verified_asset_identifier_mapping(self):
        result, bind = self.run_plan([self.path])
        self.assertEqual(result[1]["choice"], "VERIFIED_NAMED_DIRECT_MAPPING_LOOKUP")
        self.assertEqual(bind.call_args.kwargs["projections"], [
            {"node_index": 1, "predicate": "https://example.org/opcuaconnectivity/hasSignalName", "as": "value_0"}])
        self.assertIsNone(bind.call_args.kwargs.get("filter_spec"))

    def test_b22_rejects_missing_or_ambiguous_mapping(self):
        for paths in ([], [self.path, self.path]):
            with self.subTest(paths=len(paths)):
                with self.assertRaisesRegex(ValueError, "No unique verified"):
                    self.run_plan(paths)

    def test_b22_rejects_wrong_join_key(self):
        wrong = {"nodes": [self.source, self.target],
                 "steps": [{**self.path["steps"][0],
                            "left_predicate": "https://example.org/dexpi/hasLocalId"}]}
        with self.assertRaisesRegex(ValueError, "No unique verified"):
            self.run_plan([wrong])



class IdentifierAntiJoinTests(unittest.TestCase):
    def setUp(self):
        self.question = ("Which DEXPI InstrumentationFunction entities have no matching "
                         "OPCUAConnectivity SignalMapping by AssetIdentifier?")
        self.source = ("dexpi", "https://example.org/shape/InstrumentationFunction")
        self.target = ("opcuaconnectivity", "https://example.org/shape/SignalMapping")
        self.left = "https://example.org/dexpi/hasAssetIdentifier"
        self.right = "https://example.org/opcuaconnectivity/hasAssetIdentifier"
        self.catalog = {"entities": [
            {"domain": self.source[0], "shape": self.source[1],
             "display_name": "InstrumentationFunction", "properties": [self.left]},
            {"domain": self.target[0], "shape": self.target[1],
             "display_name": "SignalMapping", "properties": [self.right]},
        ]}
        self.path = {"nodes": [self.source, self.target],
                     "steps": [{"kind": "mapping", "mapping_id": "M1",
                                "left_predicate": self.left,
                                "right_predicate": self.right}]}

    def test_b30_planner_uses_verified_mapping_and_returns_source_only(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_identifier_anti_join)
        with patch("process_sim.dtwise.experimental_multihop_cli.enumerate_evidenced_paths",
                   return_value=[self.path]), patch(
                   "process_sim.dtwise.experimental_multihop_cli.bind_evidenced_path",
                   return_value={"entities": [], "edges": [], "projections": []}), patch(
                   "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                   side_effect=lambda plan, index, mappings: plan), patch(
                   "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"):
            plan, selection = _plan_named_identifier_anti_join(
                self.question, self.catalog, [], [self.source, self.target],
                {"dexpi", "opcuaconnectivity"}, {})
        self.assertEqual(selection["choice"], "VERIFIED_IDENTIFIER_ANTI_JOIN")
        self.assertEqual(plan["anti_join"], {"from": "n0", "to": "n1"})
        self.assertEqual(plan["projections"], [])
        self.assertTrue(plan["return_entities"])

    def test_b30_rejects_unverified_join(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_identifier_anti_join)
        with patch("process_sim.dtwise.experimental_multihop_cli.enumerate_evidenced_paths",
                   return_value=[]):
            with self.assertRaisesRegex(ValueError, "unique verified"):
                _plan_named_identifier_anti_join(
                    self.question, self.catalog, [], [self.source, self.target],
                    {"dexpi", "opcuaconnectivity"}, {})

    def test_b30_compiler_emits_correlated_not_exists(self):
        from process_sim.dtwise.graph_compiler import compile_graph_ir
        plan = {
            "ir_version": "1.0",
            "entities": [
                {"alias": "n0", "domain": self.source[0], "shape": self.source[1]},
                {"alias": "n1", "domain": self.target[0], "shape": self.target[1]}],
            "edges": [{"kind": "mapping", "from": "n0", "to": "n1",
                       "mapping_id": "M1", "left_predicate": self.left,
                       "right_predicate": self.right}],
            "projections": [], "filters": None, "operation": {"type": "select"},
            "return_entities": True, "anti_join": {"from": "n0", "to": "n1"}}
        schema = {"shape_paths": [
            {"domain": self.source[0], "node_shape": self.source[1],
             "path": self.left, "evidence": ["e1"]},
            {"domain": self.target[0], "node_shape": self.target[1],
             "path": self.right, "evidence": ["e2"]}],
            "relationships": []}
        mappings = [{"id": "M1", "verified": True, "evidence_ids": ["e1"],
                     "left_domain": self.source[0], "right_domain": self.target[0],
                     "left_property": self.left, "right_property": self.right}]
        query = compile_graph_ir(plan, schema, mappings=mappings,
                                 include_graph=False)
        self.assertIn("SELECT DISTINCT ?n0", query)
        self.assertIn("FILTER NOT EXISTS", query)
        self.assertIn("STR(?anti_key) = STR(?anti_other)", query)
        self.assertIn("GRAPH ?graph_n0", query)
        self.assertIn("GRAPH ?graph_n1", query)
        with self.assertRaisesRegex(ValueError, "graph provenance"):
            compile_graph_ir(plan, schema, mappings=mappings, include_graph=True)



class NamedSubstringLookupTests(unittest.TestCase):
    def setUp(self):
        self.predicate = "https://example.org/productcatalog/hasManufacturerName"
        self.entity = {
            "domain": "ProductCatalog", "shape": "https://example.org/shapes/Product",
            "display_name": "Product", "properties": [self.predicate]}
        self.catalog = {"entities": [self.entity]}
        self.anchors = [("ProductCatalog", self.entity["shape"])]
        self.question = ("Which ProductCatalog Product entities have a "
                         "ManufacturerName containing Endress?")

    def test_b33_contains_filter_preserved(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_substring_lookup)
        with patch("process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"), patch(
                "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                side_effect=lambda plan, index, mappings: plan):
            plan, selection = _plan_named_substring_lookup(
                self.question, self.catalog, {"productcatalog"},
                self.anchors, {}, [])
        self.assertEqual(selection["choice"], "VERIFIED_NAMED_SUBSTRING_LOOKUP")
        self.assertEqual(plan["filters"], {
            "op": "contains", "entity": "n0",
            "predicate": self.predicate, "value": "Endress"})
        self.assertTrue(plan["return_entities"])
        self.assertEqual(plan["projections"][0]["predicate"], self.predicate)

    def test_b33_missing_property_fails_closed(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_substring_lookup)
        self.entity["properties"] = []
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            _plan_named_substring_lookup(
                self.question, self.catalog, {"productcatalog"},
                self.anchors, {}, [])

    def test_b33_does_not_accept_unrelated_question(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_substring_lookup)
        self.assertIsNone(_plan_named_substring_lookup(
            "Which ProductCatalog Product entities have a ManufacturerName equal to Endress?",
            self.catalog, {"productcatalog"}, self.anchors, {}, []))



class DomainRegexLookupTests(unittest.TestCase):
    def test_b34_preserves_question_mark_quantifier_and_all_shape_owners(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_domain_regex_lookup)
        from process_sim.dtwise.graph_compiler import compile_graph_ir
        predicate = "https://example.org/ecad/hasLocalId"
        catalog = {"entities": [
            {"domain": "ECAD", "shape": "https://example.org/shape/A",
             "properties": [predicate]},
            {"domain": "ECAD", "shape": "https://example.org/shape/B",
             "properties": [predicate]},
            {"domain": "DEXPI", "shape": "https://example.org/shape/C",
             "properties": [predicate]}]}
        question = ("Which ECAD entities have a LocalId matching "
                    "the regular expression ^PI-?")
        plan, selection = _plan_domain_regex_lookup(
            question, catalog, {"ecad"})
        self.assertEqual(selection["choice"], "VERIFIED_DOMAIN_REGEX_LOOKUP")
        self.assertEqual(plan["domain_regex"]["pattern"], "^PI-?")
        self.assertEqual(len(plan["domain_regex"]["paths"]), 2)
        schema = {"shape_paths": [
            {"domain": e["domain"], "node_shape": e["shape"],
             "path": predicate, "evidence": ["e"]}
            for e in catalog["entities"]]}
        query = compile_graph_ir(plan, schema, include_graph=False)
        self.assertIn('REGEX(STR(?regex_value), "^PI-?")', query)
        self.assertIn("UNION", query)
        self.assertIn("SELECT DISTINCT ?entity", query)

    def test_b34_missing_property_fails_closed(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_domain_regex_lookup)
        with self.assertRaisesRegex(ValueError, "No evidenced domain property"):
            _plan_domain_regex_lookup(
                "Which ECAD entities have a LocalId matching the regular expression ^PI-?",
                {"entities": [{"domain": "ECAD", "shape": "https://example.org/A",
                               "properties": []}]}, {"ecad"})



class CaseInsensitiveSubstringTests(unittest.TestCase):
    def test_b35_preserves_case_insensitive_contains(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_substring_lookup)
        from process_sim.dtwise.graph_compiler import compile_graph_ir
        predicate = "https://example.org/assetinventory/hasAssetName"
        entity = {"domain": "AssetInventory",
                  "shape": "https://example.org/shapes/Asset",
                  "display_name": "Asset", "properties": [predicate]}
        question = ("Which AssetInventory Asset entities have an "
                    "AssetName containing reactor, ignoring case?")
        with patch("process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"), patch(
                "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                side_effect=lambda plan, index, mappings: plan):
            plan, selection = _plan_named_substring_lookup(
                question, {"entities": [entity]}, {"assetinventory"},
                [(entity["domain"], entity["shape"])], {}, [])
        self.assertEqual(selection["choice"], "VERIFIED_NAMED_SUBSTRING_LOOKUP")
        self.assertEqual(plan["filters"]["value"], "reactor")
        self.assertTrue(plan["filters"]["ignore_case"])
        schema = {"shape_paths": [
            {"domain": "AssetInventory", "node_shape": entity["shape"],
             "path": predicate, "evidence": ["e"]}]}
        query = compile_graph_ir(plan, schema, include_graph=False)
        self.assertIn("CONTAINS(LCASE(STR(", query)
        self.assertIn('LCASE("reactor")', query)

    def test_b33_remains_case_sensitive(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_named_substring_lookup)
        predicate = "https://example.org/productcatalog/hasManufacturerName"
        entity = {"domain": "ProductCatalog",
                  "shape": "https://example.org/shapes/Product",
                  "display_name": "Product", "properties": [predicate]}
        with patch("process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"), patch(
                "process_sim.dtwise.experimental_multihop_cli.resolve_shapes",
                side_effect=lambda plan, index, mappings: plan):
            plan, _ = _plan_named_substring_lookup(
                "Which ProductCatalog Product entities have a ManufacturerName containing Endress?",
                {"entities": [entity]}, {"productcatalog"},
                [(entity["domain"], entity["shape"])], {}, [])
        self.assertNotIn("ignore_case", plan["filters"])



class DomainBothPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.left = "https://example.org/dexpi/hasAssetIdentifier"
        self.right = "https://example.org/dexpi/hasLocalId"
        self.shape = "https://example.org/shape/Instrumentation"
        self.catalog = {"entities": [{
            "domain": "DEXPI", "shape": self.shape,
            "properties": [self.left, self.right]}]}
        self.schema = {"shape_paths": [
            {"domain": "DEXPI", "node_shape": self.shape,
             "path": p, "evidence": ["e"]}
            for p in (self.left, self.right)]}
        self.question = "Which DEXPI entities have both AssetIdentifier and LocalId?"

    def test_b36_both_properties_same_entity(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_domain_both_properties)
        from process_sim.dtwise.graph_compiler import compile_graph_ir
        plan, selection = _plan_domain_both_properties(self.question, self.catalog)
        self.assertEqual(selection["choice"], "VERIFIED_DOMAIN_BOTH_PROPERTIES")
        query = compile_graph_ir(plan, self.schema, include_graph=False)
        self.assertIn("SELECT DISTINCT ?entity", query)
        self.assertIn(self.left, query)
        self.assertIn(self.right, query)
        self.assertEqual(query.count("?entity <"), 2)
        self.assertNotIn("UNION", query)

    def test_b36_missing_property_fails_closed(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_domain_both_properties)
        self.catalog["entities"][0]["properties"] = [self.left]
        with self.assertRaisesRegex(ValueError, "distinct evidenced predicates"):
            _plan_domain_both_properties(self.question, self.catalog)

    def test_b36_rejects_unevidenced_predicate(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            _plan_domain_both_properties)
        from process_sim.dtwise.unified_ir import validate_ir
        plan, _ = _plan_domain_both_properties(self.question, self.catalog)
        plan["domain_both_properties"]["paths"][1][0][1] = (
            "https://example.org/dexpi/fabricated")
        with self.assertRaisesRegex(ValueError, "evidenced owners"):
            validate_ir(plan, self.schema)



class PlanningModeIsolationTests(unittest.TestCase):
    def test_llm_first_bypasses_template_planners(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            plan_experimental_multihop)
        entity = {"domain": "AssetInventory", "shape": "urn:shape:Asset",
                  "display_name": "Asset", "properties": []}
        question = ("Which AssetInventory Asset entities have an "
                    "AssetName containing reactor, ignoring case?")
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value={"entities": [entity]}), patch(
                "process_sim.dtwise.experimental_multihop_cli._focused_catalog",
                return_value=({}, [])), patch(
                "process_sim.dtwise.experimental_multihop_cli._plan_named_substring_lookup",
                side_effect=AssertionError("Template invoked")), patch(
                "process_sim.dtwise.experimental_multihop_cli.check_semantic_coverage"), patch(
                "process_sim.dtwise.experimental_evidence_selection.select_evidence_plan",
                return_value=({"ir_version": "1.0"}, {"choice": "LLM"})) as selected:
            plan, selection = plan_experimental_multihop(
                question, {}, [], model="mock", ollama_host="http://localhost",
                timeout=1, planning_mode="llm_first")
        self.assertEqual(selection["choice"], "LLM")
        selected.assert_called_once()

    def test_invalid_planning_mode_fails_closed(self):
        from process_sim.dtwise.experimental_multihop_cli import (
            plan_experimental_multihop)
        with self.assertRaisesRegex(ValueError, "Unsupported experimental planning mode"):
            plan_experimental_multihop(
                "question", {}, [], model="mock", ollama_host="http://localhost",
                timeout=1, planning_mode="unknown")


if __name__ == "__main__":
    unittest.main()
