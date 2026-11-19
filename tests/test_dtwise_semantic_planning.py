"""Regression tests for the compositional evidence-grounded semantic IR."""
import unittest

from process_sim.dtwise.semantic_planning import (
    build_evidence_catalog, validate_semantic_plan,
)


class SemanticPlanningTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence_catalog({
            "entities": [
                {"domain": "ECAD", "shape": "urn:Device",
                 "properties": ["urn:hasAddress", "urn:hasLocalId"]},
                {"domain": "ECAD", "shape": "urn:Other",
                 "properties": ["urn:hasAddress"]},
            ],
            "shacl_edges": [],
        })
        self.device = next(x["id"] for x in self.evidence.entities
                           if x["shape"] == "urn:Device")
        self.props = {x["predicate"]: x["id"] for x in self.evidence.properties
                      if x["entity_id"] == self.device}

    def plan(self, where, *, operation="select_entities", projections=None):
        return {"version": "2.0", "scope": [self.device],
                "operation": operation, "projections": projections or [],
                "where": where}

    def test_and_or_not_are_compositional(self):
        address, local = self.props["urn:hasAddress"], self.props["urn:hasLocalId"]
        for operator in ("and", "or"):
            where = {"operator": operator, "conditions": [
                {"operator": "exists", "property_id": address},
                {"operator": "not", "condition": {
                    "operator": "not_exists", "property_id": local}},
            ]}
            self.assertEqual(
                validate_semantic_plan(self.plan(where), self.evidence)["where"],
                where)

    def test_absence_and_presence(self):
        where = {"operator": "and", "conditions": [
            {"operator": "exists", "property_id": self.props["urn:hasAddress"]},
            {"operator": "not_exists", "property_id": self.props["urn:hasLocalId"]},
        ]}
        self.assertEqual(validate_semantic_plan(self.plan(where), self.evidence)["where"],
                         where)

    def test_invented_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invented property"):
            validate_semantic_plan(self.plan({
                "operator": "exists", "property_id": "P999"}), self.evidence)

    def test_other_shape_property_cannot_be_used(self):
        other = next(x["id"] for x in self.evidence.properties
                     if x["entity_id"] != self.device)
        with self.assertRaisesRegex(ValueError, "outside selected scope"):
            validate_semantic_plan(self.plan({
                "operator": "exists", "property_id": other}), self.evidence)

    def test_projection_is_not_presence(self):
        address = self.props["urn:hasAddress"]
        with self.assertRaisesRegex(ValueError, "cannot project"):
            validate_semantic_plan(self.plan(None, projections=[address]), self.evidence)
        result = validate_semantic_plan(
            self.plan(None, operation="select_values", projections=[address]),
            self.evidence)
        self.assertEqual(result["projections"], [address])

    def test_null_equality_rejected(self):
        with self.assertRaisesRegex(ValueError, "scalar literal"):
            validate_semantic_plan(self.plan({
                "operator": "eq", "property_id": self.props["urn:hasAddress"],
                "value": None}), self.evidence)

    def test_catalog_ids_are_stable_across_input_order(self):
        original = {"entities": [
            {"domain": "ECAD", "shape": "urn:Device",
             "properties": ["urn:hasLocalId", "urn:hasAddress"]},
            {"domain": "ECAD", "shape": "urn:Other",
             "properties": ["urn:hasAddress"]}], "shacl_edges": []}
        self.assertEqual(build_evidence_catalog(original), self.evidence)


if __name__ == "__main__":
    unittest.main()
