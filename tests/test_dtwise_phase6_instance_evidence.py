import unittest
from unittest.mock import patch
from experiments.dtwise_phase6_instance_evidence import (
    iri, probe_predicate, probe_identifier_overlap,
)


class InstanceEvidenceTests(unittest.TestCase):
    def test_reject_unsafe_iri(self):
        with self.assertRaises(ValueError):
            iri("https://example.org/x> ?s ?p ?o")

    @patch("experiments.dtwise_phase6_instance_evidence.sparql_select")
    def test_count_query(self, select):
        select.return_value = [{"count": "3"}]
        item = probe_predicate("http://localhost/repositories/AAS", "https://example.org/x", 5)
        self.assertEqual(item["triple_count"], 3)
        self.assertIn("COUNT(*)", select.call_args.args[1])

    @patch("experiments.dtwise_phase6_instance_evidence.sparql_select")
    def test_overlap_only_literal_hypothesis(self, select):
        select.return_value = [{"identifier": "PI-1101", "leftResources": "1",
                                "rightResources": "1"}]
        rows = probe_identifier_overlap("http://localhost/repositories/AAS",
                                        "https://example.org/a", "https://example.org/b", 5, 10)
        self.assertEqual(len(rows), 1)
        query = select.call_args.args[1]
        self.assertIn("FILTER(isLiteral(?identifier))", query)
        self.assertIn("LIMIT 10", query)


if __name__ == "__main__":
    unittest.main()
