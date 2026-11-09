"""Offline checks for the paper evaluation's provenance and time-selection rules."""

# Created: 2026-11-02
# Author: Harish
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tep_nexus_paper_evaluation.py"
spec = importlib.util.spec_from_file_location("paper_eval", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PaperEvaluationTests(unittest.TestCase):
    def test_four_assets_resolve_from_aas(self):
        root = Path(__file__).resolve().parents[1]
        result = module.engineering_evidence(
            root / "examples/aas/asset_inventory_instance.json",
            root / "examples/aas/product_catalog_instance.json")
        self.assertEqual(set(result), {"pressure", "flow", "temperature", "level"})
        self.assertEqual(result["pressure"]["signal"], "XMEAS7")
        self.assertEqual(result["flow"]["signal"], "XMEAS6")
        self.assertEqual(result["temperature"]["signal"], "XMEAS9")
        self.assertEqual(result["level"]["signal"], "XMEAS8")
        self.assertTrue(all(v["qudt_product_specification"] for v in result.values()))

    def test_unverified_joins_not_marked_as_passed(self):
        rows = module.evaluate({}, None)
        self.assertEqual(len(rows), 10)
        for index in (1, 2, 3, 6, 7, 10):
            self.assertEqual(rows[index - 1]["status"], "CROSS_DOMAIN_QUERY_NOT_RUN")
        for row in rows:
            self.assertEqual(row["answer_correctness"], "NOT_ASSESSED")

    def test_missing_fault_run_not_fabricated(self):
        rows = module.evaluate({}, None)
        self.assertEqual(rows[7]["status"], "NOT_EXECUTED")
        self.assertEqual(rows[8]["status"], "NOT_EXECUTED")


if __name__ == "__main__":
    unittest.main()
