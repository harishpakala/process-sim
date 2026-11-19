"""Offline evidence-ID retrieval tests for large SHACL catalogs."""
import json
import unittest

from process_sim.dtwise.semantic_v2_retrieval import retrieve_shape_nodes


class SemanticV2RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [
            {"domain": "opc", "shape": f"urn:Shape{i}",
             "display_name": f"Shape{i}", "properties": ["urn:hasName"]}
            for i in range(33)]}

    def retrieve(self, responses):
        calls = []
        def request(url, payload, timeout):
            calls.append(payload)
            return {"message": {"content": json.dumps(responses[min(
                len(calls) - 1, len(responses) - 1)])}}
        result = retrieve_shape_nodes(
            "Find the requested shape", self.catalog, model="mock",
            request_json=request, ollama_host="http://localhost:11434",
            timeout=1)
        return result, calls

    def test_large_catalog_uses_llm_selected_evidence_ids(self):
        result, calls = self.retrieve([{"shape_ids": ["S0", "S1"]}])
        self.assertEqual(result, [("opc", "urn:Shape0"),
                                  ("opc", "urn:Shape1")])
        self.assertEqual(len(calls), 1)

    def test_invalid_id_gets_one_llm_retry(self):
        result, calls = self.retrieve([
            {"shape_ids": ["S99"]}, {"shape_ids": ["S2"]}])
        self.assertEqual(result, [("opc", "urn:Shape10")])
        self.assertEqual(len(calls), 2)

    def test_invented_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "after two attempts"):
            self.retrieve([{"shape_ids": ["S999"]}])

    def test_small_catalog_skips_retrieval_call(self):
        catalog = {"entities": self.catalog["entities"][:1]}
        result = retrieve_shape_nodes(
            "Any question", catalog, model="mock",
            request_json=lambda *args: self.fail("LLM should not be called"),
            ollama_host="http://localhost:11434", timeout=1)
        self.assertEqual(result, [("opc", "urn:Shape0")])


if __name__ == "__main__":
    unittest.main()
