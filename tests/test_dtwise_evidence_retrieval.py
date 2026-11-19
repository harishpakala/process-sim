"""Tests for generic bounded evidence retrieval."""
import unittest

from process_sim.dtwise.semantic_planning import build_evidence_catalog
from process_sim.dtwise.evidence_retrieval import retrieve_evidence


class EvidenceRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_evidence_catalog({
            "entities": [
                {"domain": "ECAD", "shape": "urn:Device",
                 "properties": ["urn:hasAddress", "urn:hasLocalId"]},
                {"domain": "DEXPI", "shape": "urn:Pump",
                 "properties": ["urn:hasPressure", "urn:hasTemperature"]},
            ],
            "shacl_edges": [{
                "domain": "ECAD", "from_shape": "urn:Device",
                "predicate": "urn:connectsTo", "to_shape": "urn:Device",
            }],
        })

    def test_retrieval_prioritizes_question_evidence(self):
        result = retrieve_evidence("ECAD Address and LocalId",
                                   self.catalog, max_entities=1, max_properties=2)
        self.assertEqual(result.entities[0]["domain"], "ECAD")
        self.assertEqual({p["label"] for p in result.properties},
                         {"hasAddress", "hasLocalId"})

    def test_candidate_ids_preserve_full_catalog_identity(self):
        result = retrieve_evidence("ECAD Address", self.catalog,
                                   max_entities=1, max_properties=1)
        original = {p["id"]: p for p in self.catalog.properties}
        self.assertEqual(len(result.properties), 1)
        self.assertEqual(result.properties[0],
                         original[result.properties[0]["id"]])

    def test_retrieval_keeps_relationship_endpoints(self):
        result = retrieve_evidence("ECAD Device connectsTo", self.catalog,
                                   max_entities=1)
        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0]["from_entity_id"],
                         result.entities[0]["id"])

    def test_invalid_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive integers"):
            retrieve_evidence("ECAD", self.catalog, max_properties=0)


if __name__ == "__main__":
    unittest.main()
