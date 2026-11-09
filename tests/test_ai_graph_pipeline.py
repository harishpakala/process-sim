"""Offline graph pipeline tests; no Ollama or GraphDB services needed."""

# Created: 2026-10-23
# Author: Harish
import json
import unittest
from urllib.parse import parse_qs

from process_sim.ai.graphdb import discover_schema
from process_sim.ai.planner import plan

class GraphPipelineTests(unittest.TestCase):
    def test_discovery_preserves_provenance(self):
        def graph(request, timeout):
            query = parse_qs(request.data.decode())["query"][0]
            self.assertIn("GRAPH ?graph", query)
            return json.dumps({"results": {"bindings": [{
                "graph": {"value": "urn:graph:engineering"},
                "predicate": {"value": "urn:predicate:tag"},
                "count": {"value": "3"}
            }]}}).encode()
        result = discover_schema("http://localhost:7200/repositories/AAS", transport=graph)
        self.assertEqual(result["observedPredicates"][0]["graph"], "urn:graph:engineering")

    def test_planner_json(self):
        def ollama(url, payload):
            self.assertTrue(url.endswith("/api/chat"))
            self.assertEqual(payload["format"], "json")
            return {"message": {"content": '{"sparql": null}'}}
        result = plan("What exists?", {"observedPredicates": []}, transport=ollama)
        self.assertIsNone(result["sparql"])

    def test_remote_ollama_rejected(self):
        with self.assertRaises(ValueError):
            plan("What exists?", {}, endpoint="https://example.org", transport=lambda *args: None)

    def test_policy_requires_parser_and_bounded_select(self):
        from process_sim.ai.sparql_policy import validate_select
        try:
            import rdflib  # noqa: F401
        except ImportError:
            with self.assertRaises(RuntimeError):
                validate_select("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
            return
        self.assertEqual(validate_select("SELECT * WHERE { ?s ?p ?o } LIMIT 10"),
                         "SELECT * WHERE { ?s ?p ?o } LIMIT 10")
        for invalid in ("SELECT * WHERE { ?s ?p ?o }",
                        "ASK { ?s ?p ?o } LIMIT 10",
                        "SELECT * WHERE { SERVICE <http://x> { ?s ?p ?o } } LIMIT 10",
                        "SELECT * WHERE { ?s ?p ?o } LIMIT 500"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_select(invalid)

if __name__ == "__main__":
    unittest.main()
