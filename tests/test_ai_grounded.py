"""Offline tests; no Ollama service or engineering-data writes required."""
import tempfile
import unittest
from pathlib import Path
from process_sim.ai.grounded import answer, retrieve

class GroundedAITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text("Reactor functional correspondence is not physical installation.\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_retrieval_has_line_provenance(self):
        result = retrieve("reactor physical installation", self.root)
        self.assertEqual((result[0].source, result[0].line), ("README.md", 1))

    def test_no_evidence_abstains_without_model_call(self):
        result = answer("unmatchedtoken", self.root, transport=lambda *_: self.fail("called model"))
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_citation_required(self):
        result = answer("reactor physical", self.root, transport=lambda *_: {"message": {"content": "Definitely installed."}})
        self.assertEqual(result["status"], "unverified")

    def test_cited_response_still_unverified(self):
        result = answer("reactor physical", self.root, transport=lambda *_: {"message": {"content": "Not established [E1]."}})
        self.assertEqual(result["status"], "cited_unverified")

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            answer("reactor physical", self.root, endpoint="https://remote.example", transport=lambda *_: {})

if __name__ == "__main__":
    unittest.main()
