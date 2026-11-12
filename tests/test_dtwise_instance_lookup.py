"""Deterministic instance lookup planning without GraphDB or a live dataset."""
import unittest

from semantic.dtwise_instance_lookup import plan_instance_lookups


class InstanceLookupTests(unittest.TestCase):
    def setUp(self):
        self.chain = ["https://example.org/model/hasAssemblies",
                      "https://example.org/model/hasAssembly",
                      "https://example.org/model/hasLabel"]
        self.candidate = {"domain": "model", "property_chain": self.chain,
                          "start_shape": "shape",
                          "status": "unresolved_instance_candidate"}

    def test_query_uses_only_indexed_predicates(self):
        result = plan_instance_lookups({"text": "the Sample Reactor"},
                                       [self.candidate])
        self.assertEqual(len(result), 1)
        query = result[0]["sparql"]
        for predicate in self.chain:
            self.assertIn("<" + predicate + ">", query)
        self.assertIn("SELECT DISTINCT ?node2 ?identity", query)
        self.assertIn('"the sample reactor"', query)
        self.assertIn('"sample reactor"', query)
        self.assertEqual(result[0]["status"], "unexecuted_instance_lookup")

    def test_no_identity_inference_or_join(self):
        result = plan_instance_lookups({"text": "Reactor"}, [self.candidate])
        self.assertNotIn("JOIN", result[0]["sparql"])
        self.assertNotIn("associated", result[0]["sparql"])
        self.assertNotIn("resolved_instance", result[0])

    def test_rejects_unsafe_iri(self):
        bad = dict(self.candidate, property_chain=["https://example.org/x> . ?a ?b ?c"])
        self.assertEqual(plan_instance_lookups({"text": "Reactor"}, [bad]), [])

    def test_deduplicates_and_is_deterministic(self):
        role = {"text": "Reactor"}
        self.assertEqual(plan_instance_lookups(role, [self.candidate, self.candidate]),
                         plan_instance_lookups(role, [self.candidate]))
        self.assertEqual(len(plan_instance_lookups(role, [self.candidate, self.candidate])), 1)

    def test_empty_role_is_unplanned(self):
        self.assertEqual(plan_instance_lookups({"text": None}, [self.candidate]), [])

    def test_single_predicate_entity_is_root(self):
        candidate = dict(self.candidate, property_chain=[self.chain[-1]])
        self.assertIn("SELECT DISTINCT ?root ?identity",
                      plan_instance_lookups({"text": "Reactor"}, [candidate])[0]["sparql"])


if __name__ == "__main__":
    unittest.main()
