"""Offline tests for the experimental LLM path selector; no Ollama required."""
import unittest

from process_sim.dtwise.evidence_path_selection import select_evidenced_path


PATHS = [
    {"nodes": [("dexpi", "urn:a"), ("dexpi", "urn:b")],
     "steps": [{"kind": "shacl", "predicate": "urn:hasB"}]},
    {"nodes": [("dexpi", "urn:b"), ("opc", "urn:c")],
     "steps": [{"kind": "mapping", "mapping_id": "verified-1",
                "left_predicate": "urn:left", "right_predicate": "urn:right"}]},
]


class EvidencePathSelectionTests(unittest.TestCase):
    def call(self, raw, paths=None):
        calls = []

        def fake_request(url, payload, timeout):
            calls.append((url, payload, timeout))
            return {"message": {"content": raw}}

        result = select_evidenced_path(
            "Find connected signal", PATHS if paths is None else paths,
            model="fake-model", request_json=fake_request, timeout=8)
        return result, calls

    def test_selects_exact_existing_path(self):
        (path, diag), calls = self.call('{"choice":"PATH_1"}')
        self.assertIs(path, PATHS[1])
        self.assertEqual(diag["status"], "selected")
        self.assertEqual(calls[0][1]["messages"][1]["role"], "user")
        self.assertIn("verified-1", calls[0][1]["messages"][1]["content"])

    def test_abstention(self):
        (path, diag), _ = self.call('{"choice":null}')
        self.assertIsNone(path)
        self.assertEqual(diag["status"], "abstained")

    def test_invented_path_id_rejected(self):
        (path, diag), _ = self.call('{"choice":"PATH_99"}')
        self.assertIsNone(path)
        self.assertEqual(diag["status"], "invalid_choice")

    def test_freeform_ir_not_accepted(self):
        (path, diag), _ = self.call('{"edges":[],"choice":"invented"}')
        self.assertIsNone(path)
        self.assertEqual(diag["status"], "invalid_choice")

    def test_invalid_json_does_not_select(self):
        (path, diag), _ = self.call("not json")
        self.assertIsNone(path)
        self.assertEqual(diag["status"], "invalid_response")

    def test_invalid_evidence_rejected_before_model_call(self):
        bad = [{"nodes": [("dexpi", "urn:a"), ("opc", "urn:b")],
                "steps": [{"kind": "mapping", "mapping_id": "fake"}]}]
        with self.assertRaises(ValueError):
            self.call('{"choice":"PATH_0"}', paths=bad)

    def test_empty_candidate_list_rejected(self):
        with self.assertRaises(ValueError):
            self.call('{"choice":null}', paths=[])


if __name__ == "__main__":
    unittest.main()
