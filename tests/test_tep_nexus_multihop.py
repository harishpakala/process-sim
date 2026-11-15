"""Isolated tests for the TEP NEXUS multi-hop planner (no DTwise imports)."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.tep_nexus_multihop import MultiHopRejected, compile_sparql, plan

QUESTION = ("Find DEXPI InstrumentationFunctions and OPCUA SignalMappings "
            "matched through AssetInventory.")
SH_PROPERTY = "http://www.w3.org/ns/shacl#property"
SH_TARGET_CLASS = "http://www.w3.org/ns/shacl#targetClass"


def schema_fixture():
    concepts, relationships, shape_paths = [], [], []
    for domain, entity in (("dexpi", "InstrumentationFunction"),
                           ("assetinventory", "Asset"),
                           ("opcuaconnectivity", "SignalMapping")):
        cls = f"https://example.org/{domain}/{entity}"
        node = f"https://example.org/shapes/{domain}/{entity}"
        prop = f"https://example.org/shapes/{domain}/{entity}/identifier"
        pred = f"https://example.org/{domain}/hasAssetIdentifier"
        concepts.append({"domain": domain, "kind": "class",
                         "uri": cls, "labels": [entity]})
        relationships.extend([
            {"domain": domain, "subject": node,
             "predicate": SH_TARGET_CLASS, "object": cls},
            {"domain": domain, "subject": node,
             "predicate": SH_PROPERTY, "object": prop},
        ])
        shape_paths.append({"domain": domain, "node_shape": node,
                            "property_shape": prop, "path": pred})
    return {"concepts": concepts, "relationships": relationships,
            "shape_paths": shape_paths}


class MultiHopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.schema = Path(self.tmp.name) / "schema.json"
        self.data = schema_fixture()
        self.save()

    def save(self):
        self.schema.write_text(json.dumps(self.data), encoding="utf-8")

    def test_b55_generates_typed_three_domain_join(self):
        result = plan(QUESTION, self.schema)
        query = compile_sparql(result)
        self.assertEqual(result["join_edges"], [[0, 1], [1, 2]])
        for domain, entity in (("dexpi", "InstrumentationFunction"),
                               ("assetinventory", "Asset"),
                               ("opcuaconnectivity", "SignalMapping")):
            self.assertIn(f"<https://example.org/{domain}/{entity}>", query)
            self.assertIn(f"<https://example.org/{domain}/hasAssetIdentifier>", query)
        self.assertEqual(query.count("?assetIdentifier ."), 3)
        self.assertIn("LIMIT 100", query)

    def test_rejects_unmentioned_bridge(self):
        with self.assertRaises(MultiHopRejected):
            plan("Find DEXPI InstrumentationFunctions and OPCUA SignalMappings.", self.schema)

    def test_rejects_missing_shacl_property_evidence(self):
        self.data["relationships"] = [r for r in self.data["relationships"]
             if not (r["domain"] == "dexpi" and r["predicate"] == SH_PROPERTY)]
        self.save()
        with self.assertRaises(MultiHopRejected):
            plan(QUESTION, self.schema)

    def test_rejects_missing_target_class(self):
        self.data["relationships"] = [r for r in self.data["relationships"]
             if not (r["domain"] == "dexpi" and r["predicate"] == SH_TARGET_CLASS)]
        self.save()
        with self.assertRaises(MultiHopRejected):
            plan(QUESTION, self.schema)

    def test_rejects_unsupported_join_plan(self):
        with self.assertRaises(MultiHopRejected):
            compile_sparql({"kind": "other"})


if __name__ == "__main__":
    unittest.main()
