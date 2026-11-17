"""Regression checks for conservative, evidence-backed NL-to-IR coverage."""
import unittest

from process_sim.dtwise.unified_answer import check_semantic_coverage


SHAPE = "urn:instrumentation-shape"
MEASURED = "https://example.org/dexpi/hasMeasuredVariable"
LOCAL = "https://example.org/dexpi/hasLocalId"
CATALOG = {"entities": [{"domain": "dexpi", "shape": SHAPE,
                         "properties": [MEASURED, LOCAL]}], "shacl_edges": []}


def plan(projections=None, filters=None, edges=None):
    return {"ir_version": "1.0",
            "entities": [{"alias": "instrument", "domain": "dexpi", "shape": SHAPE}],
            "edges": edges if edges is not None else [],
            "projections": projections if projections is not None else [
                {"entity": "instrument", "predicate": MEASURED, "as": "measuredVariable"}],
            "filters": filters, "operation": {"type": "select"},
            "return_entities": False}


class SemanticCoverageTests(unittest.TestCase):
    def test_b03_direct_projection_accepted(self):
        check_semantic_coverage(plan(),
            "List MeasuredVariable of DEXPI InstrumentationFunctions.", CATALOG, {"dexpi"})

    def test_b03_unrequested_edge_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unrequested SHACL traversal"):
            check_semantic_coverage(plan(edges=[{"kind": "shacl"}]),
                "List MeasuredVariable of DEXPI InstrumentationFunctions.", CATALOG, {"dexpi"})

    def test_b03_unrequested_filter_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unrequested filter"):
            check_semantic_coverage(
                plan(filters={"op": "eq", "entity": "instrument",
                              "predicate": MEASURED, "value": "MeasuredVariable"}),
                "List MeasuredVariable of DEXPI InstrumentationFunctions.",
                CATALOG, {"dexpi"})

    def test_b08_missing_filter_rejected(self):
        with self.assertRaisesRegex(ValueError, "filter omitted"):
            check_semantic_coverage(plan(),
                "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
                CATALOG, {"dexpi"})

    def test_b08_wrong_literal_rejected(self):
        with self.assertRaisesRegex(ValueError, "filter literal omitted"):
            check_semantic_coverage(plan(filters={"op": "eq", "entity": "instrument",
                "predicate": LOCAL, "value": "FI_104"}),
                "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
                CATALOG, {"dexpi"})

    def test_b08_class_name_is_not_relationship_projection(self):
        catalog = {"entities": [{"domain": "dexpi", "shape": SHAPE,
                   "properties": [MEASURED, LOCAL,
                                  "https://example.org/dexpi/hasInstrumentationFunction"]}],
                   "shacl_edges": [{"domain": "dexpi", "from_shape": "urn:parent",
                       "to_shape": SHAPE,
                       "predicate": "https://example.org/dexpi/hasInstrumentationFunction"}]}
        check_semantic_coverage(plan(filters={"op": "eq", "entity": "instrument",
            "predicate": LOCAL, "value": "FI_103"}),
            "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
            catalog, {"dexpi"})

    def test_b08_valid_filter_accepted(self):
        check_semantic_coverage(plan(filters={"op": "eq", "entity": "instrument",
            "predicate": LOCAL, "value": "FI_103"}),
            "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
            CATALOG, {"dexpi"})


if __name__ == "__main__":
    unittest.main()
