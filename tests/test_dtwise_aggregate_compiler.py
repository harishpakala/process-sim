"""Offline compiler tests for grounded aggregation and sorting."""
import unittest

from process_sim.dtwise.graph_compiler import compile_graph_ir


class AggregateCompilerTests(unittest.TestCase):
    def setUp(self):
        self.predicate = "https://example.org/test/hasAssetIdentifier"
        self.schema = {
            "shape_paths": [{
                "domain": "test", "node_shape": "https://example.org/test/Shape",
                "path": self.predicate, "evidence": ["test-evidence"]
            }],
            "relationships": [],
        }
        self.plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "n0", "domain": "test",
                          "shape": "https://example.org/test/Shape"}],
            "edges": [], "projections": [], "filters": None,
            "operation": {"type": "count"}, "return_entities": False,
        }

    def compile(self):
        return compile_graph_ir(self.plan, self.schema, include_graph=False)

    def test_count_distinct_entities(self):
        query = self.compile()
        self.assertIn("COUNT(DISTINCT ?n0)", query)

    def test_group_count(self):
        self.plan["operation"] = {"type": "group_count"}
        self.plan["projections"] = [
            {"entity": "n0", "predicate": self.predicate, "as": "value_0"}]
        query = self.compile()
        self.assertIn("GROUP BY ?value_0", query)
        self.assertIn("COUNT(DISTINCT ?n0)", query)

    def test_group_count_having(self):
        self.plan["operation"] = {"type": "group_count", "having_min": 3}
        self.plan["projections"] = [
            {"entity": "n0", "predicate": self.predicate, "as": "value_0"}]
        self.assertIn("HAVING(COUNT(DISTINCT ?n0) > 3)", self.compile())

    def test_order_limit(self):
        self.plan["operation"] = {"type": "select"}
        self.plan["projections"] = [
            {"entity": "n0", "predicate": self.predicate, "as": "value_0"}]
        self.plan["order_by"] = [{"as": "value_0", "direction": "asc"}]
        self.plan["result_limit"] = 10
        query = self.compile()
        self.assertIn("ORDER BY ASC(?value_0)", query)
        self.assertIn("LIMIT 10", query)

    def test_invalid_having_threshold(self):
        self.plan["operation"] = {"type": "group_count", "having_min": -1}
        self.plan["projections"] = [
            {"entity": "n0", "predicate": self.predicate, "as": "value_0"}]
        with self.assertRaisesRegex(ValueError, "threshold"):
            self.compile()


if __name__ == "__main__":
    unittest.main()
