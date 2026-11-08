"""Mocked GraphDB discovery checks: discovery never certifies a mapping."""

# Created: 2026-10-30
# Author: Harish
import unittest

from process_sim.selira.graphdb_discovery import inspect_xmeas7


class GraphDBDiscoveryTests(unittest.TestCase):
    def test_matching_triples_remain_uncertified(self):
        rows = [
            {"s": "urn:asset:XMEAS7", "p": "https://example.org/assetinventory/hasAssetId",
             "o": "TEP_XMEAS7", "g": "urn:graph:inventory"},
            {"s": "urn:device:XMEAS7", "p": "https://example.org/ecad/hasTag",
             "o": "XMEAS7", "g": "urn:graph:ecad"},
        ]
        result = inspect_xmeas7("http://graphdb/repositories/AAS",
                                query_fn=lambda endpoint: rows)
        self.assertEqual(result["counts"]["ecad"], 1)
        self.assertEqual(result["counts"]["assetinventory"], 1)
        self.assertEqual(result["engineeringCertification"], "U")
        self.assertFalse(result["authorization"])
        self.assertEqual(len(result["facts"]["ecad"]), 1)

    def test_empty_results_do_not_authorize(self):
        result = inspect_xmeas7("http://graphdb/repositories/AAS",
                                query_fn=lambda endpoint: [])
        self.assertEqual(result["status"], "DISCOVERY_ONLY")
        self.assertFalse(result["authorization"])
        self.assertEqual(sum(result["counts"].values()), 0)

    def test_malformed_result_rejected(self):
        with self.assertRaises(ValueError):
            inspect_xmeas7("http://graphdb/repositories/AAS",
                           query_fn=lambda endpoint: [{"p": "bad"}])


if __name__ == "__main__":
    unittest.main()
