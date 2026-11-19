"""Offline evidence-path tests; no Ollama, GraphDB, or planner changes."""
import unittest

from process_sim.dtwise.unified_answer import enumerate_evidenced_paths


class EvidencePathTests(unittest.TestCase):
    def setUp(self):
        self.a = ("dexpi", "urn:dexpi:Plant")
        self.b = ("dexpi", "urn:dexpi:Instrument")
        self.c = ("opcuaconnectivity", "urn:opc:Signal")
        self.d = ("opcuaconnectivity", "urn:opc:Tag")
        self.catalog = {
            "entities": [
                {"domain": self.a[0], "shape": self.a[1],
                 "properties": ["urn:dexpi:hasInstrument"]},
                {"domain": self.b[0], "shape": self.b[1],
                 "properties": ["urn:dexpi:hasAssetIdentifier"]},
                {"domain": self.c[0], "shape": self.c[1],
                 "properties": ["urn:opc:hasAssetIdentifier", "urn:opc:hasTag"]},
                {"domain": self.d[0], "shape": self.d[1], "properties": []},
            ],
            "shacl_edges": [
                {"domain": "dexpi", "from_shape": self.a[1],
                 "to_shape": self.b[1], "predicate": "urn:dexpi:hasInstrument"},
                {"domain": "opcuaconnectivity", "from_shape": self.c[1],
                 "to_shape": self.d[1], "predicate": "urn:opc:hasTag"},
            ],
        }
        self.mapping = {
            "id": "verified-asset", "verified": True, "evidence_ids": ["e1"],
            "left_domain": "dexpi", "right_domain": "opcuaconnectivity",
            "left_property": "urn:dexpi:hasAssetIdentifier",
            "right_property": "urn:opc:hasAssetIdentifier",
        }

    def paths(self, start=None, end=None, mappings=None, **kwargs):
        return enumerate_evidenced_paths(
            self.catalog, [self.mapping] if mappings is None else mappings,
            self.a if start is None else start,
            self.d if end is None else end, **kwargs)

    def test_three_hop_shacl_mapping_shacl(self):
        paths = self.paths()
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]["nodes"], [self.a, self.b, self.c, self.d])
        self.assertEqual([s["kind"] for s in paths[0]["steps"]],
                         ["shacl", "mapping", "shacl"])
        self.assertEqual(paths[0]["steps"][1]["mapping_id"], "verified-asset")

    def test_reverse_mapping_not_inferred(self):
        self.assertEqual(self.paths(start=self.c, end=self.b), [])

    def test_unverified_mapping_excluded(self):
        self.assertEqual(self.paths(mappings=[dict(self.mapping, verified=False)]), [])
        self.assertEqual(self.paths(mappings=[dict(self.mapping, evidence_ids=[])]), [])

    def test_mapping_property_must_be_owned(self):
        self.assertEqual(self.paths(mappings=[
            dict(self.mapping, left_property="urn:dexpi:notOwned")]), [])

    def test_shacl_property_must_be_owned(self):
        catalog = dict(self.catalog)
        catalog["shacl_edges"] = [
            dict(self.catalog["shacl_edges"][0], predicate="urn:dexpi:notOwned"),
            self.catalog["shacl_edges"][1],
        ]
        self.assertEqual(enumerate_evidenced_paths(
            catalog, [self.mapping], self.a, self.d), [])

    def test_hop_bound_enforced(self):
        self.assertEqual(self.paths(max_hops=2), [])
        self.assertEqual(len(self.paths(max_hops=3)), 1)

    def test_missing_endpoint_returns_no_paths(self):
        self.assertEqual(self.paths(end=("ecad", "urn:ecad:Missing")), [])

    def test_invalid_bounds_rejected(self):
        with self.assertRaises(ValueError):
            self.paths(max_hops=0)
        with self.assertRaises(ValueError):
            self.paths(max_paths=0)


if __name__ == "__main__":
    unittest.main()
