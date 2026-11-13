"""Compiler contract tests using synthetic ontology evidence, not instance data.

These tests intentionally avoid GraphDB and Ollama. They verify deterministic
SPARQL assembly after an explicit semantic selection has been supplied.
"""
import unittest

from semantic.dtwise_sparql_compiler import compile_sparql

NS = "https://example.org/ecad/"
COLLECTION = NS + "hasDevices"
EDGE = NS + "hasDevice"
IDENTIFIER = NS + "hasAssetIdentifier"
LOCAL = NS + "hasLocalIdentifier"


def selection(question, intent="lookup", uri=IDENTIFIER, paths=None):
    if paths is None:
        paths = [{"property_chain": [COLLECTION, EDGE, uri],
                  "complete_to_root": True}]
    return {
        "question": question, "intent": intent, "join_status": "unverified",
        "selected_concepts": [{"domain": "ecad", "kind": "property",
                               "uri": uri, "paths": paths}],
        "value_constraints": [],
    }


class CompilerContractTests(unittest.TestCase):
    def test_lookup_is_deterministic_and_shacl_grounded(self):
        chosen = selection("Show ECAD asset identifiers")
        a = compile_sparql(chosen, limit=25)
        b = compile_sparql(chosen, limit=25)
        self.assertEqual(a, b)
        self.assertEqual(a["chosen_path"], [COLLECTION, EDGE, IDENTIFIER])
        self.assertIn("SELECT DISTINCT ?value", a["sparql"])
        self.assertIn("LIMIT 25", a["sparql"])
        self.assertIn("<" + IDENTIFIER + ">", a["sparql"])
        self.assertEqual(a["execution_status"], "not_executed")

    def test_count_values_uses_distinct_values(self):
        result = compile_sparql(selection("Count ECAD asset identifiers", "count"),
                                index={"concepts": []})
        self.assertEqual(result["count_target"], "value")
        self.assertIn("COUNT(DISTINCT ?value)", result["sparql"])

    def test_exists_uses_ask(self):
        result = compile_sparql(selection("Are there ECAD asset identifiers?", "exists"))
        self.assertTrue(result["sparql"].startswith("ASK WHERE"))
        self.assertNotIn("LIMIT", result["sparql"])

    def test_entity_count_requires_grounded_edge(self):
        # The selected identifier traversal supplies a root collection.
        # The entity edge is separately grounded in indexed SHACL paths.
        index = {
            "concepts": [{"domain": "ecad", "kind": "property", "uri": EDGE}],
            "shape_paths": [
                {"domain": "ecad", "path": EDGE,
                 "node_shape": "urn:device-parent",
                 "property_shape": "urn:device-edge"},
                {"domain": "ecad", "path": COLLECTION,
                 "node_shape": "urn:root",
                 "property_shape": "urn:collection-edge"},
            ],
            "relationships": [
                {"domain": "ecad", "subject": "urn:collection-edge",
                 "predicate": "http://www.w3.org/ns/shacl#node",
                 "object": "urn:device-parent"},
            ],
        }
        result = compile_sparql(selection("Count ECAD devices", "count"),
                                index=index)
        self.assertEqual(result["count_target"], "entity")
        self.assertIn("COUNT(DISTINCT ?entity)", result["sparql"])
        self.assertEqual(result["chosen_path"], [COLLECTION, EDGE])

    def test_entity_count_without_grounding_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "No grounded entity path"):
            compile_sparql(selection("Count ECAD devices", "count"),
                           index={"concepts": [], "shape_paths": [],
                                  "relationships": []})

    def test_incomplete_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "No complete SHACL traversal"):
            compile_sparql(selection("Show ECAD identifiers", paths=[
                {"property_chain": [IDENTIFIER], "complete_to_root": False}
            ]))

    def test_cross_domain_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "Cross-domain traversal"):
            compile_sparql(selection("Show ECAD identifiers", paths=[
                {"property_chain": [COLLECTION,
                                    "https://example.org/dexpi/hasEquipment",
                                    IDENTIFIER], "complete_to_root": True}
            ]))

    def test_mismatched_terminal_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not terminate"):
            compile_sparql(selection("Show ECAD identifiers", paths=[
                {"property_chain": [COLLECTION, EDGE, LOCAL],
                 "complete_to_root": True}
            ]))

    def test_value_constraints_fail_closed(self):
        chosen = selection("ECAD identifiers equal to X")
        chosen["value_constraints"] = [{"value": "X"}]
        with self.assertRaisesRegex(ValueError, "Value constraints"):
            compile_sparql(chosen)

    def test_exact_identifier_filter_is_grounded(self):
        question = "Show ECAD asset identifiers equal to https://aas.example.com/FI101"
        chosen = selection(question)
        chosen["value_constraints"] = [
            {"text": "https://aas.example.com/FI101", "role": "hasAssetIdentifier"}]
        result = compile_sparql(chosen)
        self.assertIn('FILTER(STR(?value) = "https://aas.example.com/FI101")',
                      result["sparql"])
        self.assertEqual(result["value_filter"]["property"], IDENTIFIER)

    def test_filter_is_supported_for_count_and_exists(self):
        for intent in ("count", "exists"):
            with self.subTest(intent=intent):
                chosen = selection("ECAD asset identifier X", intent)
                chosen["value_constraints"] = [
                    {"text": "X", "role": "hasAssetIdentifier"}]
                result = compile_sparql(chosen, index={"concepts": []})
                self.assertIn('FILTER(STR(?value) = "X")', result["sparql"])

    def test_invented_value_is_rejected(self):
        chosen = selection("Show ECAD asset identifiers")
        chosen["value_constraints"] = [
            {"text": "invented", "role": "hasAssetIdentifier"}]
        with self.assertRaisesRegex(ValueError, "not present"):
            compile_sparql(chosen)

    def test_filter_role_must_match_selected_property(self):
        chosen = selection("Show ECAD asset identifiers equal to X")
        chosen["value_constraints"] = [
            {"text": "X", "role": "hasLocalIdentifier"}]
        with self.assertRaisesRegex(ValueError, "does not match"):
            compile_sparql(chosen)

    def test_multiple_constraints_fail_closed(self):
        chosen = selection("ECAD asset identifier X or Y")
        chosen["value_constraints"] = [
            {"text": "X", "role": "hasAssetIdentifier"},
            {"text": "Y", "role": "hasAssetIdentifier"}]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            compile_sparql(chosen)

    def test_filter_literal_is_escaped(self):
        chosen = selection('ECAD asset identifier A" ) . ?x ?y ?z')
        chosen["value_constraints"] = [
            {"text": 'A" ) . ?x ?y ?z', "role": "hasAssetIdentifier"}]
        result = compile_sparql(chosen)
        self.assertIn('A\\\" ) . ?x ?y ?z', result["sparql"])
        self.assertEqual(result["sparql"].count("FILTER("), 1)

    def test_join_not_implicitly_approved(self):
        chosen = selection("Show ECAD identifiers")
        chosen["join_status"] = "verified"
        with self.assertRaisesRegex(ValueError, "Unexpected join status"):
            compile_sparql(chosen)

    def test_unsupported_intent_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported intent"):
            compile_sparql(selection("Update ECAD identifiers", "update"))

    def test_limit_validation(self):
        for bad in (0, -1, 10001, 1.5, "100"):
            with self.subTest(limit=bad), self.assertRaises(ValueError):
                compile_sparql(selection("Show ECAD identifiers"), limit=bad)

    def test_unsafe_iri_rejected(self):
        malicious = NS + "hasAssetIdentifier> . ?s ?p ?o"
        with self.assertRaises(ValueError):
            compile_sparql(selection("Show ECAD identifiers", uri=malicious,
                paths=[{"property_chain": [COLLECTION, EDGE, malicious],
                        "complete_to_root": True}]))


if __name__ == "__main__":
    unittest.main()
