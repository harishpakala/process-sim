import unittest

from process_sim.selira.graphdb_correspondence import (
    build_query, search_correspondence,
)


class CrossDomainDiscoveryTests(unittest.TestCase):
    def test_query_searches_all_three_identifiers(self):
        query = build_query()
        for identifier in ("pi_101", "pi-1101", "i10.19"):
            self.assertIn(identifier, query)
        self.assertIn("GRAPH ?g", query)

    def test_results_never_authorize(self):
        row = {"s": "urn:example", "p": "https://example.org/dexpi/tag",
               "o": "PI_101", "g": "urn:graph"}
        result = search_correspondence(
            "http://localhost:7200/repositories/AAS",
            query_fn=lambda endpoint, query: [row],
        )
        self.assertEqual(result["counts"]["dexpi"], 1)
        self.assertEqual(result["engineeringCertification"], "U")
        self.assertFalse(result["authorization"])

    def test_empty_results_remain_unknown(self):
        result = search_correspondence("http://localhost:7200/repositories/AAS",
                                       query_fn=lambda *args: [])
        self.assertEqual(sum(result["counts"].values()), 0)
        self.assertFalse(result["authorization"])

    def test_incomplete_binding_rejected(self):
        with self.assertRaises(ValueError):
            search_correspondence("http://localhost:7200/repositories/AAS",
                                  query_fn=lambda *args: [{"s": "urn:x"}])


if __name__ == "__main__":
    unittest.main()
