import unittest

from process_sim.selira.graphdb_relationships import (
    extract_seeds, neighborhood_query, traverse_correspondence,
)


class RelationshipTraversalTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "status": "CROSS_DOMAIN_DISCOVERY_ONLY",
            "source": "http://localhost:7200/repositories/AAS",
            "facts": {
                "dexpi": [{"s": "http://org.example.com/dexpi/PI_101"}],
                "ecad": [{"s": "http://org.example.com/ecad/PI-1101"}],
                "other": [{"s": "http://org.example.com/aas/leaf"}],
            },
        }

    def test_seeds_ignore_generic_aas_leaves(self):
        seeds = extract_seeds(self.report)
        self.assertEqual(len(seeds), 2)
        self.assertNotIn("http://org.example.com/aas/leaf", seeds)

    def test_query_rejects_injection(self):
        with self.assertRaises(ValueError):
            neighborhood_query(["http://example.org/x> } UNION { ?a ?b ?c"])

    def test_traversal_two_hops_and_never_authorizes(self):
        calls = []
        def fake(endpoint, query):
            calls.append(query)
            if len(calls) == 1:
                return [{"s": "http://org.example.com/dexpi/PI_101",
                         "p": "https://example.org/dexpi/hasLink",
                         "o": "http://org.example.com/linked/device", "g": "urn:g"}]
            return [{"s": "http://org.example.com/linked/device",
                     "p": "https://example.org/ecad/hasTag",
                     "o": "PI-1101", "g": "urn:g"}]
        result = traverse_correspondence(self.report, query_fn=fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result["facts"]), 2)
        self.assertFalse(result["authorization"])
        self.assertEqual(result["engineeringCertification"], "U")

    def test_empty_seed_result_withholds(self):
        self.report["facts"] = {}
        result = traverse_correspondence(self.report,
                                         query_fn=lambda *args: self.fail())
        self.assertEqual(result["status"], "NO_SEEDS")
        self.assertFalse(result["authorization"])

    def test_malformed_bindings_rejected(self):
        with self.assertRaises(ValueError):
            traverse_correspondence(self.report,
                                    query_fn=lambda *args: [{"s": "x"}])


if __name__ == "__main__":
    unittest.main()
