"""Regression checks for inferred SHACL two-key identifier bridges."""
import unittest
from pathlib import Path

from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import _candidates
from process_sim.dtwise.multihop_projection import (
    plan_multihop_projection, compile_multihop_projection)
from process_sim.dtwise.sparql_generator import iri
from process_sim.dtwise.rdf_executor import build_answer

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "semantic" / "ontology" / "dtwise" / "dtwise-schema-index.json"
QUESTION = ("Show the product identifiers, manufacturer names, and product "
            "descriptions of products associated with DEXPI instrumentation functions.")


class MultihopProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = Schema(str(SCHEMA))
        cls.catalog = _candidates(cls.schema)

    def test_infers_asset_inventory_bridge_and_three_outputs(self):
        plan = plan_multihop_projection(QUESTION, self.catalog, self.schema)
        self.assertIsNotNone(plan)
        self.assertEqual([s["domain"] for s in plan["sides"]],
                         ["dexpi", "assetinventory", "productcatalog"])
        self.assertEqual(plan["join_keys"], ["AssetIdentifier", "ProductIdentifier"])
        self.assertEqual({p["label"] for p in plan["projections"]},
                         {"ProductIdentifier", "ManufacturerName", "ProductDescription"})
        sparql = compile_multihop_projection(
            plan, self.schema, 100, "all_named", None, False, False, iri)
        self.assertIn("?joinKey0", sparql)
        self.assertIn("?joinKey1", sparql)
        self.assertEqual(sparql.count("GRAPH ?graph"), 3)
        for name in ("hasAssetIdentifier", "hasProductIdentifier",
                     "hasManufacturerName", "hasProductDescription"):
            self.assertIn(name, sparql)

    def test_no_inferred_bridge_without_relationship_request(self):
        self.assertIsNone(plan_multihop_projection(
            "List DEXPI instrumentation functions.", self.catalog, self.schema))

    def test_formats_three_projected_product_properties(self):
        plan = plan_multihop_projection(QUESTION, self.catalog, self.schema)
        self.assertIsNotNone(plan)
        answer = build_answer([{"value0": "ACME", "value1": "Description",
                                "value2": "P-001"}], plan)
        self.assertEqual(answer["count"], 1)
        self.assertEqual(answer["join_type"], "shacl_multihop_identifier_join")
        self.assertEqual(set(answer["values"][0]["properties"]),
                         {p["predicate"] for p in plan["projections"]})

    def test_rejects_unexpected_multihop_result_columns(self):
        plan = plan_multihop_projection(QUESTION, self.catalog, self.schema)
        with self.assertRaises(ValueError):
            build_answer([{"value0": "only one"}], plan)

    def test_compiler_rejects_tampered_projection(self):
        plan = plan_multihop_projection(QUESTION, self.catalog, self.schema)
        self.assertIsNotNone(plan)
        plan["projections"][0]["predicate"] = "https://example.org/fake"
        with self.assertRaises(ValueError):
            compile_multihop_projection(
                plan, self.schema, 100, "all_named", None, False, False, iri)


if __name__ == "__main__":
    unittest.main()
