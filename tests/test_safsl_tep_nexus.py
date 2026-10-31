"""Read-only integration tests against checked-in TEP NEXUS AAS templates."""
import unittest
from selira_integration.lifecycle import Snapshot
from process_sim.safsl.shacl.tep_nexus import (
    real_contract_source, verify_real_contract, evaluate_snapshot
)


class TestTepNexusBridge(unittest.TestCase):
    def test_real_template_ids_and_fields(self):
        refs = verify_real_contract(real_contract_source())
        self.assertEqual(refs["assets"], "https://example.org/sm/asset-inventory-template")
        self.assertEqual(refs["products"], "https://example.org/sm/product-catalog-template")

    def test_complete_unique_match(self):
        snap = Snapshot("r1", {"asset1": "A-1"}, {"product1": "A-1"}, complete=True)
        self.assertEqual(evaluate_snapshot(snap), {"asset1": "V"})

    def test_incomplete_evidence_unknown(self):
        snap = Snapshot("r1", {"asset1": "A-1"}, {}, complete=False)
        self.assertEqual(evaluate_snapshot(snap), {"asset1": "U"})

    def test_two_products_invalid(self):
        snap = Snapshot("r1", {"asset1": "A-1"},
                        {"product1": "A-1", "product2": "A-1"}, complete=True)
        self.assertEqual(evaluate_snapshot(snap), {"asset1": "F"})

    def test_no_assigned_assets(self):
        snap = Snapshot("r1", {}, {"product1": "A-1"}, complete=True)
        self.assertEqual(evaluate_snapshot(snap), {})


if __name__ == "__main__":
    unittest.main()
