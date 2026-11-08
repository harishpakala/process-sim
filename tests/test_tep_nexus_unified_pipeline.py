"""Offline checks for unified TEP NEXUS snapshot artifacts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from tep_nexus_fault_relative_query import write_snapshot_artifacts
from tep_nexus_grounded_explanation import generate
from test_tep_nexus_grounded_explanation import fixtures


class UnifiedPipelineTests(unittest.TestCase):
    def test_same_snapshot_in_query_analysis_and_explanation(self):
        query, analysis = fixtures()
        explanation = generate(query, analysis, ollama_url=None)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reports" / "tep_nexus_fault_relative_query.json"
            write_snapshot_artifacts(path, query, analysis, "<html>timeline</html>", explanation)
            saved_query = json.loads(path.read_text(encoding="utf-8"))
            saved_analysis = json.loads(
                path.with_name("tep_nexus_fault_relative_analysis.json").read_text(encoding="utf-8"))
            saved_explanation = json.loads(
                path.with_name("tep_nexus_grounded_explanation.json").read_text(encoding="utf-8"))
            markdown = path.with_name("tep_nexus_grounded_explanation.md").read_text(encoding="utf-8")
            self.assertEqual(saved_query["temporalEvidence"]["runId"],
                             saved_explanation["facts"]["runId"])
            self.assertEqual(saved_analysis[0]["sampleCount"],
                             saved_explanation["facts"]["windows"][0]["sampleCount"])
            self.assertEqual(saved_query["temporalEvidence"]["latestPersisted"],
                             saved_explanation["facts"]["latestPersisted"])
            self.assertIn("REVIEW_REQUIRED", markdown)
            self.assertIn("NOT_REQUESTED", markdown)

    def test_skip_explanation_writes_only_existing_artifacts(self):
        query, analysis = fixtures()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tep_nexus_fault_relative_query.json"
            write_snapshot_artifacts(path, query, analysis, "<html></html>", None)
            self.assertTrue(path.exists())
            self.assertFalse(path.with_name("tep_nexus_grounded_explanation.json").exists())


if __name__ == "__main__":
    unittest.main()
