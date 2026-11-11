import unittest
from unittest.mock import patch
from experiments.dtwise_phase7b_ecad_path_audit import compile_probes, inspect

ASSET = "https://aas.example.com/FI106"

class Phase7BECADTests(unittest.TestCase):
    def test_all_probes_read_only_and_named_graph_scoped(self):
        probes = compile_probes(ASSET)
        self.assertEqual(set(probes), {"devices", "collection_outgoing",
                                       "collection_incoming", "plc_endpoints"})
        for query in probes.values():
            self.assertIn("GRAPH ?graph", query)
            self.assertIn("SELECT DISTINCT", query)
            self.assertNotIn("INSERT", query)
            self.assertNotIn("DELETE", query)

    def test_no_cross_domain_join(self):
        for query in compile_probes(ASSET).values():
            self.assertNotIn("dexpi:", query)
            self.assertNotIn("assetinventory:", query)
            self.assertNotIn("owl:sameAs", query)

    def test_escaping(self):
        self.assertIn('test\\"x', compile_probes('test"x')["devices"])

    def test_rejects_unsafe_input(self):
        with self.assertRaises(ValueError):
            compile_probes("bad\nvalue")
        with self.assertRaises(ValueError):
            compile_probes(ASSET, graph="https://example.org/a> }")
        with self.assertRaises(ValueError):
            compile_probes(ASSET, limit=0)

    @patch("experiments.dtwise_phase7b_ecad_path_audit.select")
    def test_report_never_claims_full_q2(self, select):
        select.return_value = []
        result = inspect(ASSET, "http://localhost:7200/repositories/AAS")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["full_q2_supported"])
        self.assertFalse(result["verified_cross_domain_identity"])
        self.assertFalse(result["router_integrated"])
        self.assertEqual(select.call_count, 4)

    @patch("experiments.dtwise_phase7b_ecad_path_audit.select")
    def test_errors_fail_closed(self, select):
        select.side_effect = ValueError("bad result")
        result = inspect(ASSET, "http://localhost:7200/repositories/AAS")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["full_q2_supported"])

if __name__ == "__main__":
    unittest.main()
