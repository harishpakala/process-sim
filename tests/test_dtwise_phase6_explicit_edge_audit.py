import unittest
from unittest.mock import patch

from experiments.dtwise_phase6_explicit_edge_audit import (
    collect_seeds, inspect, neighbors, safe_iri,
)


class ExplicitEdgeAuditTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "named_graphs": True,
            "identifier_resource_matches": [
                {"family": "asset", "identifier": "FI106", "status": "ok",
                 "matches": [{"subject": {"type": "uri", "value": "https://example.org/a"}},
                             {"subject": {"type": "uri", "value": "https://example.org/a"}}]}
            ],
            "relationship_observations": [
                {"predicate": "https://example.org/hasTechnicalProperties",
                 "status": "ok", "observations": [
                    {"subject": {"type": "uri", "value": "https://example.org/a"},
                     "object": {"type": "uri", "value": "https://example.org/props"}}]}
            ],
        }

    def test_accepts_normal_resource_iri(self):
        self.assertEqual(safe_iri("https://example.org/a"), "<https://example.org/a>")
        self.assertEqual(safe_iri("https://example.org/resource"), "<https://example.org/resource>")

    def test_rejects_unsafe_iri(self):
        with self.assertRaises(ValueError):
            safe_iri("https://example.org/x> ?s ?p ?o")

    def test_requires_named_graph_source(self):
        with self.assertRaises(ValueError):
            collect_seeds({"named_graphs": False}, 5)

    def test_deduplicates_within_seed_group(self):
        seeds = collect_seeds(self.source, 5)
        self.assertEqual(seeds["asset:FI106"], ["https://example.org/a"])

    @patch("experiments.dtwise_phase6_explicit_edge_audit.query")
    def test_neighbor_query_uses_graph_and_resource(self, query):
        query.return_value = []
        neighbors("http://localhost:7200/repositories/AAS",
                  "https://example.org/a", "incoming", 10, 5)
        self.assertIn("GRAPH ?graph", query.call_args.args[1])
        self.assertIn("?subject ?predicate <https://example.org/a>",
                      query.call_args.args[1])

    @patch("experiments.dtwise_phase6_explicit_edge_audit.neighbors")
    def test_no_inferred_identity_or_membership(self, neighbors):
        neighbors.return_value = []
        result = inspect("http://localhost:7200/repositories/AAS", self.source)
        self.assertFalse(result["verified_cross_domain_identity"])
        self.assertFalse(result["verified_physical_membership"])
        self.assertEqual(len(result["resource_audits"]), 2)


if __name__ == "__main__":
    unittest.main()
