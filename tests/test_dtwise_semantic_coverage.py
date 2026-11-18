"""Regression checks for conservative, evidence-backed NL-to-IR coverage."""
import unittest
import base64

from process_sim.dtwise.unified_answer import (check_semantic_coverage,
                                              catalog_from_schema)


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


class ShapeCatalogMetadataTests(unittest.TestCase):
    def test_encoded_shape_exposes_readable_metadata_without_replacing_iri(self):
        source = "InstrumentationFunctions.InstrumentationFunction/nodeShape"
        encoded = base64.urlsafe_b64encode(source.encode()).decode().rstrip("=")
        shape = "http://org.example.com/namespace/" + encoded
        index = {"shape_paths": [
            {"domain": "dexpi", "node_shape": shape, "path": MEASURED,
             "property_shape": "urn:property", "evidence": ["urn:source"]}
        ], "relationships": []}
        entity = catalog_from_schema(index)["entities"][0]
        self.assertEqual(entity["shape"], shape)
        self.assertEqual(entity["display_name"], "InstrumentationFunction")
        self.assertEqual(entity["source_path"],
                         "InstrumentationFunctions.InstrumentationFunction")
        self.assertEqual(entity["properties"], [MEASURED])

    def test_unrecognized_shape_iri_remains_unmodified(self):
        index = {"shape_paths": [
            {"domain": "dexpi", "node_shape": SHAPE, "path": MEASURED,
             "property_shape": "urn:property", "evidence": ["urn:source"]}
        ], "relationships": []}
        entity = catalog_from_schema(index)["entities"][0]
        self.assertEqual(entity["shape"], SHAPE)
        self.assertNotIn("display_name", entity)
        self.assertNotIn("source_path", entity)


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

    def test_with_literal_is_filter_not_projection(self):
        check_semantic_coverage(
            plan(filters={"op": "eq", "entity": "instrument",
                          "predicate": LOCAL, "value": "FI_103"}),
            "Show MeasuredVariable belonging to DEXPI InstrumentationFunction entities with LocalId FI_103.",
            CATALOG, {"dexpi"})

    def test_with_uri_literal_must_match_full_value(self):
        uri = "https://aas.example.com/FI103"
        question = ("Show MeasuredVariable belonging to DEXPI InstrumentationFunction "
                    "entities with LocalId " + uri + ".")
        check_semantic_coverage(
            plan(filters={"op": "eq", "entity": "instrument",
                          "predicate": LOCAL, "value": uri}),
            question, CATALOG, {"dexpi"})
        with self.assertRaisesRegex(ValueError, "Explicit input constraint omitted"):
            check_semantic_coverage(
                plan(filters={"op": "eq", "entity": "instrument",
                              "predicate": LOCAL, "value": "https://aas"}),
                question, CATALOG, {"dexpi"})

    def test_with_literal_does_not_hide_missing_output(self):
        with self.assertRaisesRegex(ValueError, "projection omitted"):
            check_semantic_coverage(
                plan(projections=[{"entity": "instrument", "predicate": LOCAL,
                                   "as": "localId"}],
                     filters={"op": "eq", "entity": "instrument",
                              "predicate": LOCAL, "value": "FI_103"}),
                "Show MeasuredVariable belonging to DEXPI InstrumentationFunction entities with LocalId FI_103.",
                CATALOG, {"dexpi"})

    def test_where_then_list_projection_is_not_a_second_filter(self):
        check_semantic_coverage(
            plan(filters={"op": "eq", "entity": "instrument",
                          "predicate": LOCAL, "value": "FI_103"}),
            "For DEXPI InstrumentationFunction entities where LocalId is FI_103, list MeasuredVariable.",
            CATALOG, {"dexpi"})

    def test_where_then_list_missing_projection_rejected(self):
        with self.assertRaisesRegex(ValueError, "projection omitted"):
            check_semantic_coverage(
                plan(projections=[{"entity": "instrument", "predicate": LOCAL,
                                   "as": "localId"}],
                     filters={"op": "eq", "entity": "instrument",
                              "predicate": LOCAL, "value": "FI_103"}),
                "For DEXPI InstrumentationFunction entities where LocalId is FI_103, list MeasuredVariable.",
                CATALOG, {"dexpi"})

    def test_b08_valid_filter_accepted(self):
        check_semantic_coverage(plan(filters={"op": "eq", "entity": "instrument",
            "predicate": LOCAL, "value": "FI_103"}),
            "Show dexpi InstrumentationFunction measuredVariable where localId is FI_103.",
            CATALOG, {"dexpi"})


if __name__ == "__main__":
    unittest.main()
