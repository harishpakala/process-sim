import unittest
from unittest.mock import patch
from experiments.dtwise_phase6g_catalog_compiler import compile_query, validate

class Phase6GCatalogCompilerTests(unittest.TestCase):
    PRODUCT = "https://example.org/product-types/EandH_TMass_F300_Candidate"

    def test_compiles_observed_predicates(self):
        q = compile_query(self.PRODUCT)
        for predicate in ("hasProductIdentifier", "hasTechnicalProperties",
                          "hasECLASSIRDI", "hasFamilyMeasuringRange",
                          "hasFamilyMeasuringRangeQUDTUnit",
                          "hasFamilyMeasuringRangeQUDTQuantityKind"):
            self.assertIn("pc:" + predicate, q)

    def test_no_unverified_cross_domain_join(self):
        q = compile_query(self.PRODUCT)
        for namespace in ("dexpi", "ecad", "assetinventory", "engineeringbom",
                          "hasIRDI", "hasQuDTAttribute", "hasCatalogTechnicalSpecification"):
            self.assertNotIn(namespace, q)

    def test_identifier_escaping(self):
        q = compile_query('test"\\literal')
        self.assertIn('test\\"\\\\literal', q)

    def test_rejects_invalid_identifier(self):
        for value in ("", "bad\nvalue", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compile_query(value)

    def test_compile_only_never_calls_graphdb(self):
        with patch("experiments.dtwise_phase6g_catalog_compiler.execute") as execute:
            result = validate(self.PRODUCT, "http://localhost/repositories/AAS", False)
        execute.assert_not_called()
        self.assertEqual(result["status"], "compiled")
        self.assertFalse(result["route_integrated"])
        self.assertFalse(result["full_q5_supported"])
        self.assertFalse(result["verified_physical_membership"])

    @patch("experiments.dtwise_phase6g_catalog_compiler.execute")
    def test_execution_preserves_binding_and_no_gold_claim(self, execute):
        execute.return_value = [{"product": {"type": "uri", "value": "https://example.org/product"}}]
        result = validate(self.PRODUCT, "http://localhost/repositories/AAS")
        self.assertEqual(result["binding_count"], 1)
        self.assertEqual(result["gold_status"], "missing_not_scored")
        self.assertFalse(result["full_q5_supported"])

if __name__ == "__main__":
    unittest.main()
