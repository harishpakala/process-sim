"""Tests for single LLM-first semantic selector and validation feedback."""
import json
import unittest

from process_sim.dtwise.semantic_selection import select_semantic_plan


class SemanticSelectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [{
            "domain": "ECAD", "shape": "urn:Device",
            "properties": ["urn:hasAddress", "urn:hasLocalId"],
        }], "shacl_edges": []}

    def test_boolean_selection_is_model_decided(self):
        for operator in ("and", "or"):
            requests = []
            def request(url, payload, timeout):
                requests.append(payload)
                ids = {p["label"]: p["id"] for p in
                       payload["messages"][1]["content"] and
                       json.loads(payload["messages"][1]["content"])["evidence"]["properties"]}
                entity_id = json.loads(payload["messages"][1]["content"])["evidence"]["entities"][0]["id"]
                return {"message": {"content": json.dumps({
                    "version": "2.0", "scope": [entity_id],
                    "operation": "select_entities", "projections": [],
                    "where": {"operator": operator, "conditions": [
                        {"operator": "exists", "property_id": ids["hasAddress"]},
                        {"operator": "exists", "property_id": ids["hasLocalId"]},
                    ]},
                })}}
            result, _ = select_semantic_plan(
                "Which ECAD entities have Address and LocalId?",
                self.catalog, model="mock", request_json=request,
                ollama_host="http://localhost", timeout=1)
            self.assertEqual(result["where"]["operator"], operator)
            self.assertEqual(len(requests), 1)

    def test_invalid_evidence_gets_feedback_and_retry(self):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            data = json.loads(payload["messages"][1]["content"])["evidence"]
            prop = data["properties"][0]["id"]
            entity = data["entities"][0]["id"]
            return {"message": {"content": json.dumps({
                "version": "2.0", "scope": [entity],
                "operation": "select_entities", "projections": [],
                "where": {"operator": "exists",
                          "property_id": "P999" if len(calls) == 1 else prop},
            })}}
        plan, _ = select_semantic_plan(
            "Which ECAD entities have Address?",
            self.catalog, model="mock", request_json=request,
            ollama_host="http://localhost", timeout=1)
        self.assertEqual(len(calls), 2)
        self.assertIn("Invented property", calls[1]["messages"][-1]["content"])
        self.assertEqual(plan["where"]["operator"], "exists")

    def test_repeated_invalid_evidence_fails_closed(self):
        def request(url, payload, timeout):
            return {"message": {"content": json.dumps({
                "version": "2.0", "scope": ["S0"],
                "operation": "select_entities", "projections": [],
                "where": {"operator": "exists", "property_id": "P999"},
            })}}
        with self.assertRaisesRegex(ValueError, "failed validation"):
            select_semantic_plan(
                "Which ECAD entities have Address?", self.catalog,
                model="mock", request_json=request,
                ollama_host="http://localhost", timeout=1)




class SemanticSelectionContractTests(unittest.TestCase):
    def test_entity_retrieval_distinct_from_projection(self):
        from process_sim.dtwise.semantic_selection import SYSTEM_PROMPT
        self.assertIn("select_entities when the user asks WHICH entities", SYSTEM_PROMPT)
        self.assertIn("select_values ONLY when the user explicitly requests property values", SYSTEM_PROMPT)
        self.assertIn("Never assume that multiple shapes imply a relationship", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
