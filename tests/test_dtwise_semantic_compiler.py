"""Compiler regression tests for compositional semantic IR."""
import unittest

from process_sim.dtwise.semantic_planning import build_evidence_catalog
from process_sim.dtwise.semantic_compiler import compile_semantic_plan


class SemanticCompilerTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence_catalog({"entities": [{
            "domain": "ECAD", "shape": "urn:Device",
            "properties": ["urn:hasAddress", "urn:hasLocalId"],
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
        self.assertIn(" UNION ", query)
        self.assertIn("FILTER NOT EXISTS", query)
        self.assertIn("urn:hasLocalId", query)

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
        self.assertIn("FILTER EXISTS", query)
        self.assertNotIn(' = "a"b"', query)

    def test_invalid_evidence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Invented property"):
            compile_semantic_plan(self.plan({
                "operator": "exists", "property_id": "P999",
            }), self.evidence)

    def test_multi_entity_requires_explicit_join(self):
        second = build_evidence_catalog({"entities": [
            {"domain": "ECAD", "shape": "urn:Device",
             "properties": ["urn:hasAddress"]},
            {"domain": "ECAD", "shape": "urn:Other",
             "properties": ["urn:hasLocalId"]},
        ], "shacl_edges": []})
        plan = {"version": "2.0", "scope": [e["id"] for e in second.entities],
                "operation": "select_entities", "projections": [], "where": None}
        with self.assertRaisesRegex(ValueError, "explicit joins"):
            compile_semantic_plan(plan, second)


if __name__ == "__main__":
    unittest.main()
