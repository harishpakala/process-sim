"""Created: 2026-10-30
Author: Harish"""

import unittest

from process_sim.selira.graphdb_expansion import expand_discovery, expansion_query


class GraphDBExpansionTests(unittest.TestCase):
    def setUp(self):
        self.discovery = {
            "signal": "XMEAS7", "status": "DISCOVERY_ONLY",
            "source": "http://localhost:7200/repositories/AAS",
            "facts": {
                "opcuaconnectivity": [{"s": "http://example.org/opc/one", "p": "p",
                                        "o": "XMEAS7", "g": "urn:g"}],
                "assetinventory": [{"s": "http://example.org/assets/two", "p": "p",
                                    "o": "XMEAS7", "g": "urn:g"}],
            },
        }

    def test_expands_both_subjects_without_authorization(self):
        seen = []
        def fake(endpoint, query):
            seen.append(query)
            return [{"s": "http://example.org/opc/one", "p": "urn:hasUnit",
                     "o": "kPa", "g": "urn:g"}]
        result = expand_discovery(self.discovery, query_fn=fake)
        self.assertIn("<http://example.org/opc/one>", seen[0])
        self.assertIn("<http://example.org/assets/two>", seen[0])
        self.assertEqual(result["engineeringCertification"], "U")
        self.assertFalse(result["authorization"])
        self.assertEqual(len(result["facts"]), 1)

    def test_rejects_unsafe_subject(self):
        with self.assertRaises(ValueError):
            expansion_query(['http://example.org/x> } UNION { ?s ?p ?o'])

    def test_no_seeds_withholds(self):
        self.discovery["facts"] = {}
        result = expand_discovery(self.discovery, query_fn=lambda *args: self.fail())
        self.assertEqual(result["status"], "NO_SEEDS")
        self.assertFalse(result["authorization"])

    def test_malformed_graphdb_binding_rejected(self):
        with self.assertRaises(ValueError):
            expand_discovery(self.discovery, query_fn=lambda *args: [{"s": "x"}])


if __name__ == "__main__":
    unittest.main()
