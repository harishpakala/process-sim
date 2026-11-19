"""Compiler regression tests for compositional semantic IR."""
import unittest

from process_sim.dtwise.semantic_planning import build_evidence_catalog
from process_sim.dtwise.semantic_compiler import compile_semantic_plan


class SemanticCompilerTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence_catalog({"entities": [{
            "domain": "ECAD", "shape": "https://example.org/Device",
            "properties": ["https://example.org/hasAddress", "https://example.org/hasLocalId"],
        }], "shacl_edges": []})
        self.entity = self.evidence.entities[0]["id"]
        self.props = {p["label"]: p["id"] for p in self.evidence.properties}

    def plan(self, where, operation="select_entities", projections=None):
        return {"version": "2.0", "scope": [self.entity],
                "operation": operation, "projections": projections or [],
                "where": where}

    def test_and_or_precedence_and_named_graphs(self):
        where = {"operator": "and", "conditions": [
            {"operator": "exists", "property_id": self.props["hasAddress"]},
            {"operator": "or", "conditions": [
                {"operator": "exists", "property_id": self.props["hasLocalId"]},
                {"operator": "not_exists", "property_id": self.props["hasAddress"]},
            ]},
        ]}
        query = compile_semantic_plan(self.plan(where), self.evidence)
        self.assertIn("SELECT DISTINCT ?entity", query)
        self.assertIn("GRAPH ?g_", query)
        self.assertIn(" || ", query)
        self.assertIn(" && ", query)
        self.assertIn("NOT EXISTS", query)
        self.assertIn("https://example.org/hasLocalId", query)

    def test_projection_and_count(self):
        query = compile_semantic_plan(
            self.plan(None, "select_values", [self.props["hasAddress"]]),
            self.evidence, graph_mode="default")
        self.assertIn("SELECT DISTINCT ?entity ?value_0", query)
        self.assertNotIn("GRAPH", query)
        count = compile_semantic_plan(
            self.plan(None, "count"), self.evidence)
        self.assertIn("COUNT(DISTINCT ?entity)", count)

    def test_comparison_literal_is_escaped(self):
        query = compile_semantic_plan(self.plan({
            "operator": "eq", "property_id": self.props["hasAddress"],
            "value": 'a"b',
        }), self.evidence)
        self.assertIn("EXISTS", query)
        self.assertNotIn(' = "a"b"', query)

    def test_invalid_evidence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Invented property"):
            compile_semantic_plan(self.plan({
                "operator": "exists", "property_id": "P999",
            }), self.evidence)

    def test_cross_shape_filters_cannot_implicitly_join(self):
        evidence = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "https://example.org/One",
             "properties": ["https://example.org/hasAddress"]},
            {"domain": "ECAD", "shape": "https://example.org/Two",
             "properties": ["https://example.org/hasLocalId"]},
        ], "shacl_edges": []})
        ids = [p["id"] for p in evidence.properties]
        plan = {"version": "2.0",
                "scope": [e["id"] for e in evidence.entities],
                "operation": "select_entities", "projections": [],
                "where": {"operator": "and", "conditions": [
                    {"operator": "exists", "property_id": ids[0]},
                    {"operator": "exists", "property_id": ids[1]},
                ]}}
        with self.assertRaisesRegex(ValueError, "distinct shapes"):
            compile_semantic_plan(plan, evidence)

    def test_verified_target_class_anchors_entity(self):
        evidence = build_evidence_catalog({"entities": [{
            "domain": "ECAD", "shape": "https://example.org/DeviceShape",
            "target_classes": ["https://example.org/Device"],
            "properties": ["https://example.org/hasAddress"],
        }], "shacl_edges": []})
        prop = evidence.properties[0]["id"]
        plan = {"version": "2.0", "scope": [evidence.entities[0]["id"]],
                "operation": "select_entities", "projections": [],
                "where": {"operator": "not_exists", "property_id": prop}}
        query = compile_semantic_plan(plan, evidence)
        self.assertIn("rdf-syntax-ns#type", query)
        self.assertIn("<https://example.org/Device>", query)
        self.assertNotIn("?anchor_", query)
        self.assertIn("NOT EXISTS", query)

    def test_independent_typed_shapes_compile_without_join(self):
        evidence = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "https://example.org/A",
             "target_classes": ["https://example.org/ClassA"],
             "properties": ["https://example.org/hasAddress"]},
            {"domain": "ECAD", "shape": "https://example.org/B",
             "target_classes": ["https://example.org/ClassB"],
             "properties": ["https://example.org/hasLocalId"]},
        ], "shacl_edges": []})
        plan = {"version": "2.0", "scope_mode": "independent",
                "scope": [e["id"] for e in evidence.entities],
                "operation": "select_entities", "projections": [],
                "where": None}
        query = compile_semantic_plan(plan, evidence)
        self.assertIn(" UNION ", query)
        self.assertIn("<https://example.org/ClassA>", query)
        self.assertIn("<https://example.org/ClassB>", query)
        self.assertEqual(query.count("SELECT DISTINCT ?entity"), 3)

    def test_independent_scope_rejects_untyped_shape(self):
        evidence = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "https://example.org/A",
             "target_classes": ["https://example.org/ClassA"],
             "properties": ["https://example.org/hasAddress"]},
            {"domain": "ECAD", "shape": "https://example.org/B",
             "properties": ["https://example.org/hasLocalId"]},
        ], "shacl_edges": []})
        plan = {"version": "2.0", "scope_mode": "independent",
                "scope": [e["id"] for e in evidence.entities],
                "operation": "select_entities", "projections": [],
                "where": None}
        with self.assertRaisesRegex(ValueError, "verified targetClass"):
            compile_semantic_plan(plan, evidence)

    def test_multi_entity_requires_explicit_join(self):
        second = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "https://example.org/Device",
             "properties": ["https://example.org/hasAddress"]},
            {"domain": "ECAD", "shape": "https://example.org/Other",
             "properties": ["https://example.org/hasLocalId"]},
        ], "shacl_edges": []})
        plan = {"version": "2.0", "scope": [e["id"] for e in second.entities],
                "operation": "select_entities", "projections": [], "where": None}
        with self.assertRaisesRegex(ValueError, "verified shape membership"):
            compile_semantic_plan(plan, second)


if __name__ == "__main__":
    unittest.main()
