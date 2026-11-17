"""Regression tests for grouped counts, HAVING, ordering, and limits."""
import unittest

from process_sim.dtwise.graph_compiler import compile_graph_ir
from process_sim.dtwise.unified_ir import validate_ir


DOMAIN = "opcua"
SHAPE = "https://example.org/SignalMappingShape"
ASSET = "https://example.org/assetIdentifier"
SIGNAL = "https://example.org/signalName"
SCHEMA = {
    "shape_paths": [
        {"domain": DOMAIN, "node_shape": SHAPE, "path": ASSET,
         "property_shape": "https://example.org/assetProperty", "evidence": ["e1"]},
        {"domain": DOMAIN, "node_shape": SHAPE, "path": SIGNAL,
         "property_shape": "https://example.org/signalProperty", "evidence": ["e2"]},
    ],
    "relationships": [],
}


def plan(predicate=ASSET):
    return {
        "ir_version": "1.0",
        "entities": [{"alias": "mapping", "domain": DOMAIN, "shape": SHAPE}],
        "edges": [],
        "projections": [{"entity": "mapping", "predicate": predicate, "as": "value"}],
        "filters": None,
        "operation": {"type": "select"},
        "return_entities": False,
    }


class QueryOperationsTests(unittest.TestCase):
    def test_grouped_count(self):
        ir = plan()
        ir["operation"] = {"type": "count", "group_by": ["value"]}
        sql = compile_graph_ir(ir, SCHEMA)
        self.assertIn("COUNT(DISTINCT ?mapping)", sql)
        self.assertIn("GROUP BY ?graph_mapping ?value", sql)
        self.assertIn("?mapping <" + ASSET + "> ?value", sql)

    def test_having(self):
        ir = plan()
        ir["operation"] = {"type": "count", "group_by": ["value"],
                           "having": {"op": "gt", "value": 3}}
        sql = compile_graph_ir(ir, SCHEMA)
        self.assertIn("HAVING (COUNT(DISTINCT ?mapping) > 3)", sql)

    def test_order_limit(self):
        ir = plan(SIGNAL)
        ir["order_by"] = [{"by": "value", "direction": "asc"}]
        ir["limit"] = 10
        sql = compile_graph_ir(ir, SCHEMA)
        self.assertIn("ORDER BY ASC(?value)", sql)
        self.assertTrue(sql.rstrip().endswith("LIMIT 10"))

    def test_reject_unprojected_group_key(self):
        ir = plan()
        ir["operation"] = {"type": "count", "group_by": ["invented"]}
        with self.assertRaises(ValueError):
            validate_ir(ir, SCHEMA)

    def test_reject_having_without_group(self):
        ir = plan()
        ir["projections"] = []
        ir["operation"] = {"type": "count", "having": {"op": "gt", "value": 3}}
        with self.assertRaises(ValueError):
            validate_ir(ir, SCHEMA)

    def test_reject_injected_order_alias(self):
        ir = plan()
        ir["order_by"] = [{"by": "value) . DROP ALL", "direction": "asc"}]
        with self.assertRaises(ValueError):
            validate_ir(ir, SCHEMA)

    def test_legacy_select(self):
        sql = compile_graph_ir(plan(), SCHEMA)
        self.assertIn("SELECT DISTINCT", sql)

    def test_legacy_global_count(self):
        ir = plan()
        ir["projections"] = []
        ir["operation"] = {"type": "count"}
        sql = compile_graph_ir(ir, SCHEMA)
        self.assertIn("COUNT(DISTINCT ?mapping)", sql)


if __name__ == "__main__":
    unittest.main()
