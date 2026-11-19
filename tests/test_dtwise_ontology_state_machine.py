"""Offline tests for opt-in ontology exploration; no Ollama or GraphDB required."""
import unittest

from process_sim.dtwise.ontology_state_machine import (
    explore_ontology_path, ollama_edge_decider,
)


class OntologyStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.a = ("D", "urn:A")
        self.b = ("D", "urn:B")
        self.c = ("D", "urn:C")
        self.catalog = {
            "entities": [
                {"domain": "D", "shape": "urn:A",
                 "properties": ["urn:toB"]},
                {"domain": "D", "shape": "urn:B",
                 "properties": ["urn:toC"]},
                {"domain": "D", "shape": "urn:C",
                 "properties": ["urn:name"]},
            ],
            "shacl_edges": [
                {"domain": "D", "from_shape": "urn:A",
                 "to_shape": "urn:B", "predicate": "urn:toB"},
                {"domain": "D", "from_shape": "urn:B",
                 "to_shape": "urn:C", "predicate": "urn:toC"},
            ],
        }
        self.projections = [
            {"node_index": 2, "predicate": "urn:name", "as": "name"}
        ]

    def test_grounded_two_hop_ir(self):
        def choose(question, evidence):
            self.assertEqual(question, "Find C names from A")
            self.assertLessEqual(len(evidence["options"]), 2)
            return {"action": "follow", "edge_id": "EDGE_0"}

        plan, diagnostics = explore_ontology_path(
            "Find C names from A", self.catalog, [], self.a, self.c,
            decide=choose, projections=self.projections)
        self.assertEqual(diagnostics["hops"], 2)
        self.assertEqual(plan["ir_version"], "1.0")
        self.assertEqual(len(plan["edges"]), 2)
        self.assertEqual(plan["projections"][0]["predicate"], "urn:name")

    def test_hallucinated_edge_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unverified edge"):
            explore_ontology_path(
                "Find C", self.catalog, [], self.a, self.c,
                decide=lambda q, e: {"action": "follow", "edge_id": "EDGE_999"},
                projections=self.projections)

    def test_abstention_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "abstained"):
            explore_ontology_path(
                "Find C", self.catalog, [], self.a, self.c,
                decide=lambda q, e: {"action": "abstain"},
                projections=self.projections)

    def test_hop_budget_enforced(self):
        with self.assertRaisesRegex(ValueError, "Hop budget"):
            explore_ontology_path(
                "Find C", self.catalog, [], self.a, self.c,
                decide=lambda q, e: {"action": "follow", "edge_id": "EDGE_0"},
                projections=self.projections, max_hops=1)

    def test_ollama_selector_json(self):
        calls = []
        def request(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"message": {"content":
                    '{"action":"follow","edge_id":"EDGE_0"}'}}
        choose = ollama_edge_decider(
            model="llama3.1:8b", request_json=request,
            ollama_host="http://localhost:11434")
        response = choose("Find C", {"options": [{"id": "EDGE_0"}]})
        self.assertEqual(response["edge_id"], "EDGE_0")
        self.assertEqual(calls[0][1]["format"], "json")


if __name__ == "__main__":
    unittest.main()
