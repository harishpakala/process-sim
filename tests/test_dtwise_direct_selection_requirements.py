"""Regression tests for SHACL-grounded direct semantic-selection requirements.

These are offline unit tests; the GraphDB/Ollama end-to-end benchmark remains
the authoritative integration check.
"""
import unittest

from process_sim.dtwise.unified_answer import extract_semantic_selection_requirements


DEXPI = "https://example.org/dexpi/"
OPCUA = "https://example.org/opcuaconnectivity/"
ECAD = "https://example.org/ecad/"


class DirectSelectionRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "entities": [
                {"domain": "dexpi", "shape": DEXPI + "InstrumentationFunctionShape",
                 "display_name": "InstrumentationFunction",
                 "properties": [DEXPI + "hasAssetIdentifier", DEXPI + "hasLocalId"]},
                {"domain": "opcuaconnectivity", "shape": OPCUA + "SignalMappingShape",
                 "display_name": "SignalMapping",
                 "properties": [OPCUA + "hasAssetIdentifier", OPCUA + "hasSignalName"]},
                {"domain": "ecad", "shape": ECAD + "DeviceShape",
                 "display_name": "Device",
                 "properties": [ECAD + "hasAssetIdentifier", ECAD + "hasLocalId"]},
            ],
            "shacl_edges": [],
        }

    def test_b44_with_entity_is_not_filter(self):
        question = ("Get OPCUAConnectivity SignalMapping SignalName associated "
                    "with DEXPI InstrumentationFunction using AssetIdentifier.")
        outputs, inputs = extract_semantic_selection_requirements(
            question, self.catalog, {"dexpi", "opcuaconnectivity"})
        self.assertEqual(outputs, [OPCUA + "hasSignalName"])
        self.assertEqual(inputs, [])

    def test_b45_with_localid_is_filter_not_output(self):
        question = ("Get OPCUAConnectivity SignalMapping SignalName for DEXPI "
                    "InstrumentationFunction with LocalId FI-001 using AssetIdentifier.")
        outputs, inputs = extract_semantic_selection_requirements(
            question, self.catalog, {"dexpi", "opcuaconnectivity"})
        self.assertEqual(outputs, [OPCUA + "hasSignalName"])
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0]["name"], "LocalId")
        self.assertEqual(inputs[0]["value"], "FI-001")
        self.assertIn({"domain": "dexpi", "predicate": DEXPI + "hasLocalId"},
                      inputs[0]["candidate_properties"])

    def test_b46_with_entity_is_not_filter(self):
        question = ("Find ECAD Device LocalId associated with DEXPI "
                    "InstrumentationFunction via AssetIdentifier.")
        outputs, inputs = extract_semantic_selection_requirements(
            question, self.catalog, {"dexpi", "ecad"})
        self.assertEqual(outputs, [ECAD + "hasLocalId"])
        self.assertEqual(inputs, [])


if __name__ == "__main__":
    unittest.main()
