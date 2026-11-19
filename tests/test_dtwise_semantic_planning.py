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

    def test_multi_shape_requires_explicit_semantics(self):
        other = next(e["id"] for e in self.evidence.entities
                     if e["id"] != self.device)
        plan = self.plan(None)
        plan["scope"] = [self.device, other]
        with self.assertRaisesRegex(ValueError, "explicit scope_mode"):
            validate_semantic_plan(plan, self.evidence)

    def test_independent_scope_requires_target_membership(self):
        other = next(e["id"] for e in self.evidence.entities
                     if e["id"] != self.device)
        plan = self.plan(None)
        plan["scope"] = [self.device, other]
        plan["scope_mode"] = "independent"
        with self.assertRaisesRegex(ValueError, "verified targetClass"):
            validate_semantic_plan(plan, self.evidence)

    def test_independent_values_rejected_before_compilation(self):
        catalog = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "https://example.org/A",
             "properties": ["https://example.org/address"],
             "target_classes": ["https://example.org/TypeA"]},
            {"domain": "ECAD", "shape": "https://example.org/B",
             "properties": ["https://example.org/localId"],
             "target_classes": ["https://example.org/TypeB"]},
        ], "shacl_edges": []})
        plan = {"version": "2.0", "scope": [e["id"] for e in catalog.entities],
                "scope_mode": "independent", "operation": "select_values",
                "projections": [p["id"] for p in catalog.properties],
                "where": None}
        with self.assertRaisesRegex(ValueError, "Independent multi-shape value projections"):
            validate_semantic_plan(plan, catalog)
        plan["operation"] = "select_entities"
        plan["projections"] = []
        self.assertEqual(validate_semantic_plan(plan, catalog)["operation"],
                         "select_entities")

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
