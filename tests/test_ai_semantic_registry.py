"""Offline tests for source-driven registry; no GraphDB/Ollama required."""
import json
import tempfile
import unittest
from pathlib import Path

from process_sim.ai.semantic_registry import build_registry, planner_context

class RegistryTests(unittest.TestCase):
    def test_lifting_rules_for_collection_and_property(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = {"submodelElements": [{"modelType": "SubmodelElementCollection",
                "idShort": "Equipments", "value": [{"modelType": "Property",
                "idShort": "AssetIdentifier", "qualifiers": [{"type": "Cardinality", "value": "One"}]}]}]}
            instance = {"submodelElements": [{"modelType": "SubmodelElementCollection",
                "idShort": "Reactor", "qualifiers": [{"type": "OntoConcept", "value": "Equipment"}],
                "value": [{"modelType": "Property", "idShort": "AssetIdentifier", "value": "R-001"}]}]}
            a, b = root / "template.json", root / "instance.json"
            a.write_text(json.dumps(template))
            b.write_text(json.dumps(instance))
            result = build_registry(targets=[("dexpi", a, b)])
            d = result["domains"][0]
            self.assertIn("https://example.org/dexpi/Equipment", d["classes"])
            preds = {p["iri"]: p for p in d["predicates"]}
            self.assertIn("https://example.org/dexpi/hasEquipment", preds)
            self.assertEqual(preds["https://example.org/dexpi/hasAssetIdentifier"]["cardinality"], "One")
            self.assertEqual(len(planner_context(result)["predicates"]), 4)

    def test_registry_rejects_oversized_context(self):
        with self.assertRaises(ValueError):
            planner_context({"domains": [{"domain": "d", "predicates": [{"iri": str(i), "kind": "literal"} for i in range(3)],
                                          "classes": []}], "aasNamespace": "urn:a", "note": ""}, max_predicates=2)

if __name__ == "__main__":
    unittest.main()
