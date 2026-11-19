"""Regression tests: projection aliases cannot collide with entity variables."""
import unittest

from process_sim.dtwise.unified_ir import validate_ir
from process_sim.dtwise.graph_compiler import compile_graph_ir


PROPERTY = "https://example.org/dexpi/hasMeasuredVariable"
SHAPE = "urn:instrumentation-shape"
SCHEMA = {
    "shape_paths": [
        {"domain": "dexpi", "node_shape": SHAPE, "path": PROPERTY,
         "evidence": ["urn:evidence:measured"]}
    ],
    "relationships": [],
}


def plan(entity_alias, output_alias):
    return {
        "ir_version": "1.0",
        "entities": [{"alias": entity_alias, "domain": "dexpi", "shape": SHAPE}],
        "edges": [],
        "projections": [
            {"entity": entity_alias, "predicate": PROPERTY, "as": output_alias}
        ],
        "filters": None,
        "operation": {"type": "select"},
        "return_entities": True,
    }


class AliasCollisionTests(unittest.TestCase):
    def test_same_entity_and_projection_alias_rejected(self):
        ir = plan("measured_variable", "measured_variable")
        with self.assertRaisesRegex(ValueError, "Projection aliases must differ"):
            validate_ir(ir, SCHEMA)
        with self.assertRaisesRegex(ValueError, "Projection aliases must differ"):
            compile_graph_ir(ir, SCHEMA, include_graph=False)

    def test_distinct_aliases_compile_to_distinct_variables(self):
        ir = plan("instrument", "measured_variable")
        validate_ir(ir, SCHEMA)
        sparql = compile_graph_ir(ir, SCHEMA, include_graph=False)
        self.assertIn("?instrument <" + PROPERTY + "> ?measured_variable .", sparql)
        self.assertNotIn("?measured_variable <" + PROPERTY + "> ?measured_variable", sparql)


if __name__ == "__main__":
    unittest.main()
