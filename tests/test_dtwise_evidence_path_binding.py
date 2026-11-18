"""Offline tests for evidence-verified multi-hop Unified IR binding."""
import unittest

from process_sim.dtwise.evidence_path_binding import bind_evidenced_path
from process_sim.dtwise.unified_answer import enumerate_evidenced_paths


class EvidencePathBindingTests(unittest.TestCase):
    def setUp(self):
        self.a = ("dexpi", "urn:Plant")
        self.b = ("dexpi", "urn:Instrument")
        self.c = ("opc", "urn:Signal")
        self.catalog = {
            "entities": [
                {"domain": "dexpi", "shape": "urn:Plant",
                 "properties": ["urn:hasInstrument"]},
                {"domain": "dexpi", "shape": "urn:Instrument",
                 "properties": ["urn:asset", "urn:localId"]},
                {"domain": "opc", "shape": "urn:Signal",
                 "properties": ["urn:opcAsset", "urn:signalName"]},
            ],
            "shacl_edges": [{"domain": "dexpi", "from_shape": "urn:Plant",
                             "to_shape": "urn:Instrument",
                             "predicate": "urn:hasInstrument"}],
        }
        self.mappings = [{"id": "asset-map", "verified": True,
                          "evidence_ids": ["e1"], "left_domain": "dexpi",
                          "right_domain": "opc", "left_property": "urn:asset",
                          "right_property": "urn:opcAsset"}]
        self.path = enumerate_evidenced_paths(
            self.catalog, self.mappings, self.a, self.c)[0]
        self.outputs = [{"node_index": 2, "predicate": "urn:signalName",
                         "as": "signal_name"}]

    def bind(self, **kwargs):
        return bind_evidenced_path(
            kwargs.pop("path", self.path),
            self.catalog, kwargs.pop("mappings", self.mappings),
            projections=kwargs.pop("projections", self.outputs), **kwargs)

    def test_two_hop_ir_preserves_verified_evidence(self):
        ir = self.bind()
        self.assertEqual(ir["ir_version"], "1.0")
        self.assertEqual([e["kind"] for e in ir["edges"]],
                         ["shacl", "mapping"])
        self.assertEqual(ir["edges"][1]["mapping_id"], "asset-map")
        self.assertEqual(ir["projections"], [
            {"entity": "n2", "predicate": "urn:signalName",
             "as": "signal_name"}])
        self.assertIsNone(ir["filters"])

    def test_filter_binds_to_correct_owner(self):
        ir = self.bind(filter_spec={"node_index": 1,
                                   "predicate": "urn:localId",
                                   "op": "eq", "value": "FI-001"})
        self.assertEqual(ir["filters"]["entity"], "n1")
        self.assertEqual(ir["filters"]["value"], "FI-001")

    def test_invented_mapping_is_rejected(self):
        path = dict(self.path, steps=[dict(s) for s in self.path["steps"]])
        path["steps"][1]["mapping_id"] = "invented"
        with self.assertRaises(ValueError):
            self.bind(path=path)

    def test_unverified_mapping_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(mappings=[dict(self.mappings[0], verified=False)])

    def test_wrong_projection_owner_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(projections=[{"node_index": 0,
                                    "predicate": "urn:signalName",
                                    "as": "name"}])

    def test_reversed_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(path={"nodes": list(reversed(self.path["nodes"])),
                            "steps": list(reversed(self.path["steps"]))})

    def test_unsupported_filter_operator_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(filter_spec={"node_index": 1,
                                   "predicate": "urn:localId",
                                   "op": "contains", "value": "FI"})

    def test_duplicate_projection_alias_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(projections=self.outputs + self.outputs)


if __name__ == "__main__":
    unittest.main()
