"""Offline tests for conservative natural-language path requirement grounding."""
import unittest

from process_sim.dtwise.evidence_path_requirements import ground_path_requirements


class EvidencePathRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [
            {"domain": "dexpi", "shape": "urn:Instrument",
             "properties": ["urn:dexpi:hasLocalId",
                            "urn:dexpi:hasAssetIdentifier"]},
            {"domain": "opcuaconnectivity", "shape": "urn:Signal",
             "properties": ["urn:opc:hasSignalName",
                            "urn:opc:hasAssetIdentifier"]},
        ], "shacl_edges": []}
        self.path = {"nodes": [
            ("dexpi", "urn:Instrument"),
            ("opcuaconnectivity", "urn:Signal")],
            "steps": [{"kind": "mapping", "mapping_id": "asset",
                       "left_predicate": "urn:dexpi:hasAssetIdentifier",
                       "right_predicate": "urn:opc:hasAssetIdentifier"}]}
        self.mentioned = {"dexpi", "opcuaconnectivity"}

    def ground(self, question, path=None):
        return ground_path_requirements(
            question, self.catalog, self.mentioned,
            self.path if path is None else path)

    def test_entity_reference_is_not_filter(self):
        outputs, filter_spec = self.ground(
            "Get OPCUAConnectivity Signal SignalName associated with "
            "DEXPI Instrument using AssetIdentifier.")
        self.assertEqual(outputs[0]["node_index"], 1)
        self.assertEqual(outputs[0]["predicate"], "urn:opc:hasSignalName")
        self.assertIsNone(filter_spec)

    def test_localid_filter_bound_to_dexpi(self):
        outputs, filter_spec = self.ground(
            "Get OPCUAConnectivity Signal SignalName for DEXPI Instrument "
            "with LocalId FI-001 using AssetIdentifier.")
        self.assertEqual(outputs[0]["node_index"], 1)
        self.assertEqual(filter_spec, {
            "node_index": 0, "predicate": "urn:dexpi:hasLocalId",
            "op": "eq", "value": "FI-001"})

    def test_missing_output_owner_rejected(self):
        path = dict(self.path, nodes=[("dexpi", "urn:Instrument")])
        with self.assertRaises(ValueError):
            self.ground("Get OPCUAConnectivity Signal SignalName.", path=path)

    def test_duplicate_output_owner_rejected(self):
        path = dict(self.path, nodes=[
            ("dexpi", "urn:Instrument"),
            ("opcuaconnectivity", "urn:Signal"),
            ("opcuaconnectivity", "urn:Signal")])
        with self.assertRaises(ValueError):
            self.ground("Get OPCUAConnectivity Signal SignalName.", path=path)

    def test_missing_output_requirement_rejected(self):
        with self.assertRaises(ValueError):
            self.ground("Find connected instruments.")

    def test_unknown_path_shape_rejected(self):
        with self.assertRaises(ValueError):
            self.ground("Get SignalName.", path={
                "nodes": [("unknown", "urn:Missing")]})


if __name__ == "__main__":
    unittest.main()
