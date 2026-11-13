"""Offline tests for opt-in SPARQL instance resolution."""
import unittest
from semantic.dtwise_instance_executor import resolve_instance_lookups

QUERY = ("SELECT DISTINCT ?node2 ?identity WHERE {\n"
         "  ?node2 <https://example.org/p> ?identity .\n} LIMIT 20")
PLAN = {"domain": "sample", "identity_property": "https://example.org/p",
        "property_chain": ["https://example.org/p"],
        "status": "unexecuted_instance_lookup", "sparql": QUERY}
ENDPOINT = "http://localhost:7200/repositories/AAS"


def row(uri, label):
    return {"node2": {"type": "uri", "value": uri},
            "identity": {"type": "literal", "value": label}}


class InstanceExecutorTests(unittest.TestCase):
    def test_unique_candidate_does_not_verify_relationship(self):
        result = resolve_instance_lookups([PLAN], ENDPOINT,
                                          query_fn=lambda *a, **k: [row("https://example.org/a", "A")])
        self.assertEqual(result["status"], "unique_candidate")
        self.assertFalse(result["relationship_verified"])
        self.assertEqual(result["candidate_instances"][0]["uri"], "https://example.org/a")

    def test_ambiguous(self):
        result = resolve_instance_lookups([PLAN], ENDPOINT,
                                          query_fn=lambda *a, **k: [row("https://example.org/b", "B"),
                                                                      row("https://example.org/a", "A")])
        self.assertEqual(result["status"], "ambiguous_candidates")
        self.assertEqual(result["candidate_instances"][0]["uri"], "https://example.org/a")

    def test_zero_matches(self):
        result = resolve_instance_lookups([PLAN], ENDPOINT,
                                          query_fn=lambda *a, **k: [])
        self.assertEqual(result["status"], "no_matches")

    def test_error_fails_closed(self):
        def fail(*a, **k):
            raise OSError("offline")
        result = resolve_instance_lookups([PLAN], ENDPOINT, query_fn=fail)
        self.assertEqual(result["status"], "execution_incomplete")
        self.assertEqual(result["candidate_instances"], [])

    def test_skips_untrusted_query_shape(self):
        plan = dict(PLAN, sparql="DELETE WHERE { ?s ?p ?o }")
        result = resolve_instance_lookups([plan], ENDPOINT,
                                          query_fn=lambda *a, **k: self.fail("should not execute"))
        self.assertEqual(result["status"], "execution_incomplete")

    def test_invalid_endpoint(self):
        with self.assertRaises(ValueError):
            resolve_instance_lookups([PLAN], "file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
