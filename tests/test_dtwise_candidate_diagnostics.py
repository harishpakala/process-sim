"""Smoke tests for the read-only DTwise candidate diagnostic tool."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dtwise_candidate_diagnostics", ROOT / "scripts/diagnose_dtwise_candidates.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CandidateDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = module.Schema(module.DEFAULT_SCHEMA)

    def test_b23_b24_b25_report_without_approval(self):
        import json
        cases = json.loads(module.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        for case in cases:
            if case["id"] not in {"B23", "B24", "B25"}:
                continue
            with self.subTest(case=case["id"]):
                result = module.analyze(case["question"], self.schema, [])
                self.assertIn("root_filter_accepted", result)
                self.assertIn("root_filter_excluded", result)
                self.assertIn("discovery_status", result)
                self.assertNotEqual(result["mapping_status"], "exactly_one_verified")

    def test_unverified_candidate_never_counts_as_approved(self):
        import json
        candidates = ROOT / "semantic/ontology2/dtwise/unified-ir-mapping-candidates.json"
        if not candidates.exists():
            self.skipTest("candidate registry is not checked out")
        cases = json.loads(module.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        b23 = next(c for c in cases if c["id"] == "B23")
        mappings = json.loads(candidates.read_text(encoding="utf-8"))
        result = module.analyze(b23["question"], self.schema, mappings)
        self.assertNotEqual(result["mapping_status"], "exactly_one_verified")


if __name__ == "__main__":
    unittest.main()
