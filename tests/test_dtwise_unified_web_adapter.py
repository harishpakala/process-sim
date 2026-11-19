"""Regression tests for the Unified IR web adapter; no live Ollama or GraphDB."""
import unittest
from unittest.mock import patch

from process_sim.api import dtwise_query


class UnifiedDtwiseWebAdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = {"GRAPHDB_SPARQL_ENDPOINT": "http://localhost:7200/repositories/AAS",
                    "DTWISE_UNIFIED_MODEL": "llama3.1:8b"}
        self.plan = {
            "ir_version": "1.0",
            "entities": [{"alias": "item", "domain": "productcatalog", "shape": "product-shape"}],
            "edges": [],
            "projections": [{"entity": "item", "predicate": "https://example.org/productcatalog/hasManufacturerPartNumber",
                             "as": "ManufacturerPartNumber"}],
            "filters": {"op": "eq", "entity": "item",
                        "predicate": "https://example.org/productcatalog/hasManufacturerName",
                        "value": "Schneider"},
            "operation": {"type": "select"},
            "return_entities": False,
        }

    def test_existing_schneider_query_uses_unified_ir(self):
        results = {"results": {"bindings": [{"ManufacturerPartNumber":
                   {"type": "literal", "value": "A9MEM3555"}}]}}
        with patch.object(dtwise_query, "SCHEMA_PATH") as schema, \
             patch.object(dtwise_query, "generate_ir", return_value=self.plan) as generate, \
             patch.object(dtwise_query, "compile_graph_ir", return_value="SELECT ?ManufacturerPartNumber WHERE {}") as compile_query, \
             patch.object(dtwise_query, "execute_select", return_value=results) as execute:
            schema.is_file.return_value = True
            response = dtwise_query.run_question(
                "Get ManufacturerPartNumber from ProductCatalog where ManufacturerName is Schneider.",
                environ=self.env)
        self.assertEqual(response["mode"], "unified_ir_graphdb")
        self.assertEqual(response["answer"]["values"][0]["value"], "A9MEM3555")
        self.assertEqual(response["answer"]["count"], 1)
        self.assertEqual(response["plan"], self.plan)
        self.assertEqual(generate.call_args.kwargs["model"], "llama3.1:8b")
        self.assertEqual(compile_query.call_args.kwargs["graph_mode"], "all_named")
        execute.assert_called_once()

    def test_invalid_ir_is_rejected_without_graphdb_execution(self):
        with patch.object(dtwise_query, "SCHEMA_PATH") as schema, \
             patch.object(dtwise_query, "generate_ir", side_effect=ValueError("SHACL rejection")), \
             patch.object(dtwise_query, "execute_select") as execute:
            schema.is_file.return_value = True
            with self.assertRaises(dtwise_query.DtwiseRejected):
                dtwise_query.run_question(
                    "Get ManufacturerPartNumber from ProductCatalog where ManufacturerName is Schneider.",
                    environ=self.env)
            execute.assert_not_called()

    def test_multiple_projection_answer_shape(self):
        plan = dict(self.plan, projections=[
            {"entity": "item", "predicate": "urn:manufacturer", "as": "ManufacturerName"},
            {"entity": "item", "predicate": "urn:part", "as": "ManufacturerPartNumber"}])
        answer = dtwise_query._answer_from_results(
            {"results": {"bindings": [{"ManufacturerName": {"value": "Schneider"},
                                      "ManufacturerPartNumber": {"value": "A9MEM3555"}}]}}, plan)
        self.assertEqual(answer["properties"], ["urn:manufacturer", "urn:part"])
        self.assertEqual(answer["values"][0]["properties"]["urn:part"], "A9MEM3555")


if __name__ == "__main__":
    unittest.main()
