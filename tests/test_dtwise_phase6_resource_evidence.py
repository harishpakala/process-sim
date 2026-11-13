import unittest
from unittest.mock import patch

from experiments.dtwise_phase6_resource_evidence import (
    inspect, observations, safe_iri, term,
)


class ResourceEvidenceTests(unittest.TestCase):
    def test_unsafe_iri_rejected(self):
        with self.assertRaises(ValueError):
            safe_iri("https://example.org/x> ?a ?b ?c")

    def test_term_preserves_type_and_datatype(self):
        self.assertEqual(
            term({"type": "literal", "value": "42",
                  "datatype": "http://www.w3.org/2001/XMLSchema#integer"}),
            {"type": "literal", "value": "42",
             "datatype": "http://www.w3.org/2001/XMLSchema#integer"})

    @patch("experiments.dtwise_phase6_resource_evidence.select")
    def test_named_graph_query(self, select):
        select.return_value = [{"subject": {"type": "uri", "value": "urn:s"},
                                "graph": {"type": "uri", "value": "urn:g"}}]
        rows = observations("http://localhost/repositories/AAS",
                            "?subject <https://example.org/p> ?object .",
                            10, 5, True)
        self.assertIn("GRAPH ?graph", select.call_args.args[1])
        self.assertEqual(rows[0]["graph"]["value"], "urn:g")

    @patch("experiments.dtwise_phase6_resource_evidence.observations")
    def test_inspection_does_not_verify_identity(self, observations):
        observations.return_value = []
        result = inspect("http://localhost/repositories/AAS")
        self.assertFalse(result["verified_cross_domain_identity"])
        self.assertFalse(result["verified_physical_membership"])
        self.assertEqual(len(result["relationship_observations"]), 4)
        self.assertEqual(len(result["identifier_resource_matches"]), 16)

    def test_limit_restricted(self):
        with self.assertRaises(ValueError):
            inspect("http://localhost/repositories/AAS", limit=101)


if __name__ == "__main__":
    unittest.main()
