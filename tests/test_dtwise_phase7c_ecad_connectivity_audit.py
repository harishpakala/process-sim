import unittest
from unittest.mock import patch
from experiments.dtwise_phase7c_ecad_connectivity_audit import compile_probes, inspect

ASSET = "https://aas.example.com/FI106"

class Phase7CConnectivityTests(unittest.TestCase):
    def test_seven_probes(self):
        probes = compile_probes(ASSET)
        self.assertEqual(len(probes), 7)
        self.assertIn("direct_device_to_plc", probes)
        self.assertIn("shared_intermediate", probes)
        self.assertIn("ecad:hasEndPoint", probes["direct_device_to_plc"])
        self.assertIn("ecad:hasPLCEndPoint", probes["direct_device_to_plc"])

    def test_read_only_and_named_graph(self):
        for sparql in compile_probes(ASSET).values():
            self.assertIn("GRAPH ?graph", sparql)
            self.assertIn("SELECT DISTINCT", sparql)
            self.assertNotIn("INSERT DATA", sparql)

    def test_no_cross_domain_join(self):
        for sparql in compile_probes(ASSET).values():
            self.assertNotIn("dexpi:", sparql)
            self.assertNotIn("owl:sameAs", sparql)

    def test_unsafe_inputs(self):
        with self.assertRaises(ValueError):
            compile_probes("x\n")
        with self.assertRaises(ValueError):
            compile_probes(ASSET, graph="https://example.org/>")
        with self.assertRaises(ValueError):
            compile_probes(ASSET, limit=0)

    @patch("experiments.dtwise_phase7c_ecad_connectivity_audit.query")
    def test_candidates_do_not_verify_connection(self, query):
        query.return_value = [{"predicate": {"type": "uri", "value": "https://example.org/ecad/test"}}]
        result = inspect(ASSET, "http://localhost:7200/repositories/AAS")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["verified_device_to_plc_connection"])
        self.assertFalse(result["full_q2_supported"])
        self.assertFalse(result["router_integrated"])
        self.assertEqual(query.call_count, 7)

    @patch("experiments.dtwise_phase7c_ecad_connectivity_audit.query")
    def test_query_failure_is_reported(self, query):
        query.side_effect = ValueError("malformed")
        result = inspect(ASSET, "http://localhost:7200/repositories/AAS")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["verified_device_to_plc_connection"])

if __name__ == "__main__":
    unittest.main()
