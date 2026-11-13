import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from experiments.dtwise_phase4_router import main, route

PRODUCT = "https://example.org/product-types/EandH_TMass_F300_Candidate"

class Phase7CatalogRouteTests(unittest.TestCase):
    def call_router(self, question, execute=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            argv = ["--question", question, "--catalog-product-identifier", PRODUCT,
                    "--output", str(path)]
            if not execute:
                argv.append("--skip-execution")
            code = main(argv)
            return code, json.loads(path.read_text(encoding="utf-8"))

    def test_opt_in_catalog_only_compiles(self):
        code, report = self.call_router("Show Product Catalog technical properties")
        self.assertEqual(code, 0)
        self.assertEqual(report["route"], "catalog_product_properties_opt_in")
        self.assertEqual(report["status"], "compiled")
        self.assertFalse(report["full_q5_supported"])
        self.assertFalse(report["verified_cross_domain_identity"])

    def test_full_q5_fails_closed(self):
        code, report = self.call_router(
            "What Product Catalog properties are associated with reactor instruments?")
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "unsupported")

    def test_installation_claim_fails_closed(self):
        code, report = self.call_router("Which Product Catalog items are installed?")
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "unsupported")

    def test_non_catalog_question_fails_closed(self):
        code, report = self.call_router("List properties")
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "unsupported")

    def test_normal_routing_unchanged(self):
        self.assertEqual(route("Which instruments are associated with reactor?"), "generic_v4_1")

    @patch("experiments.dtwise_phase4_router.validate_catalog")
    def test_opt_in_execution_delegates(self, validate):
        validate.return_value = {"status": "executed", "binding_count": 1,
                                 "full_q5_supported": False}
        code, report = self.call_router("Show Product Catalog ECLASS properties", execute=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["binding_count"], 1)
        validate.assert_called_once()

if __name__ == "__main__":
    unittest.main()
