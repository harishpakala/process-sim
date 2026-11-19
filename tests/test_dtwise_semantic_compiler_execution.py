"""Optional end-to-end SPARQL semantics checks using a local RDF dataset.

Requires rdflib with SPARQL support; no GraphDB writes or network calls.
"""
import unittest

from process_sim.dtwise.semantic_compiler import compile_semantic_plan
from process_sim.dtwise.semantic_planning import build_evidence_catalog

try:
    from rdflib import Dataset, URIRef, Literal
except ImportError:
    Dataset = None


@unittest.skipIf(Dataset is None, "rdflib is not installed")
class SemanticCompilerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.data = Dataset()
        self.ns = "https://example.org/"
        graph = self.data.graph(URIRef(self.ns + "graph"))
        self.entities = [URIRef(self.ns + x) for x in ("both", "address", "local")]
        graph.add((self.entities[0], URIRef(self.ns + "hasAddress"), Literal("A")))
        graph.add((self.entities[0], URIRef(self.ns + "hasLocalId"), Literal("L")))
        graph.add((self.entities[1], URIRef(self.ns + "hasAddress"), Literal("A")))
        graph.add((self.entities[2], URIRef(self.ns + "hasLocalId"), Literal("L")))
        self.evidence = build_evidence_catalog({"entities": [{
            "domain": "ECAD", "shape": self.ns + "Device",
            "properties": [self.ns + "hasAddress", self.ns + "hasLocalId"],
        }], "shacl_edges": []})
        self.scope = [self.evidence.entities[0]["id"]]
        self.ids = {p["label"]: p["id"] for p in self.evidence.properties}

    def run_plan(self, condition):
        plan = {"version": "2.0", "scope": self.scope,
                "operation": "select_entities", "projections": [],
                "where": condition}
        query = compile_semantic_plan(plan, self.evidence)
        return {row[0] for row in self.data.query(query)}

    def presence(self, label, op="exists"):
        return {"operator": op, "property_id": self.ids[label]}

    def test_and_or_not_across_named_graphs(self):
        both, address, local = self.entities
        self.assertEqual(self.run_plan({"operator": "and", "conditions": [
            self.presence("hasAddress"), self.presence("hasLocalId")]}), {both})
        self.assertEqual(self.run_plan({"operator": "or", "conditions": [
            self.presence("hasAddress"), self.presence("hasLocalId")]}),
            {both, address, local})
        self.assertEqual(self.run_plan({"operator": "and", "conditions": [
            self.presence("hasAddress"),
            {"operator": "not", "condition": self.presence("hasLocalId")}]}
        ), {address})
        self.assertEqual(self.run_plan({"operator": "and", "conditions": [
            self.presence("hasAddress"),
            self.presence("hasLocalId", "not_exists")]}), {address})


if __name__ == "__main__":
    unittest.main()
