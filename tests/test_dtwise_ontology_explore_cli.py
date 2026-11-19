"""Offline CLI adapter tests using a minimal SHACL index and fake Ollama."""
import json
import unittest

from process_sim.dtwise.ontology_explore_cli import plan_ontology_explore


class OntologyExploreAdapterTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "shape_paths": [
                {"domain": "D", "node_shape": "urn:A",
                 "path": "urn:name", "evidence": True,
                 "property_shape": "urn:psA"},
                {"domain": "D", "node_shape": "urn:B",
                 "path": "urn:other", "evidence": True,
                 "property_shape": "urn:psB"},
            ],
            "relationships": [],
        }

    def run_plan(self, answer):
        def fake_request(url, payload, timeout):
            return {"message": {"content": json.dumps(answer)}}
        return plan_ontology_explore(
            "Get name from A", self.index, [], model="fake",
            ollama_host="http://localhost:11434", timeout=1,
            request_json=fake_request)

    def test_direct_property_creates_existing_ir(self):
        plan, meta = self.run_plan({
            "source": "S0", "target": "S0", "property": "S0P0",
            "operation": "select", "filter": None})
        self.assertEqual(plan["ir_version"], "1.0")
        self.assertEqual(plan["edges"], [])
        self.assertEqual(plan["projections"][0]["predicate"], "urn:name")
        self.assertEqual(meta["hops"], 0)

    def test_property_owner_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.run_plan({
                "source": "S0", "target": "S1", "property": "S0P0",
                "operation": "select", "filter": None})

    def test_grounding_instrumentation_and_domain_focus(self):
        observed = []
        metrics = {}
        def request(url, payload, timeout):
            observed.append(json.loads(payload['messages'][1]['content']))
            return {'message': {'content': json.dumps({
                'source': 'S0', 'target': 'S0', 'property': 'S0P0',
                'operation': 'select', 'filter': None})},
                'prompt_eval_count': 15, 'eval_count': 8}
        plan, details = plan_ontology_explore(
            'Get name from D A', self.index, [], model='fake',
            ollama_host='http://localhost:11434', timeout=1,
            request_json=request, prompt_diagnostics=metrics)
        self.assertEqual(details['metrics']['llm_calls'], 1)
        self.assertEqual(details['metrics']['prompt_tokens'], 15)
        self.assertEqual(details['metrics']['generated_tokens'], 8)
        self.assertEqual(len(observed), 1)

    def test_unsupported_operation_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not support"):
            self.run_plan({
                "source": "S0", "target": "S0", "property": "S0P0",
                "operation": "unsupported", "filter": None})


if __name__ == "__main__":
    unittest.main()
