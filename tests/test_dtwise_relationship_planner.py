"""Regression contracts for relationship questions; no dataset or Ollama."""
import unittest
from unittest.mock import patch

from semantic.dtwise_relationship_planner import (
    is_relationship_question, plan_relationship)
from semantic.dtwise_sparql_compiler import compile_sparql

QUESTION = ("Which process instruments are associated with the Tennessee "
            "Eastman Process reactor, according to the integrated "
            "engineering representations?")
P = "https://example.org/dexpi/hasEngineeringInterpretationNote"


class RelationshipPlannerTests(unittest.TestCase):
    def test_tep_question_is_relationship_intent(self):
        self.assertTrue(is_relationship_question(QUESTION))

    def test_tep_never_compiles_engineering_note_lookup(self):
        selection = {
            "question": QUESTION, "intent": "lookup",
            "join_status": "unverified", "value_constraints": [],
            "selected_concepts": [{
                "uri": P, "domain": "dexpi", "kind": "property",
                "paths": [{"complete_to_root": True,
                           "property_chain": [
                               "https://example.org/dexpi/hasActuatingFunctions",
                               "https://example.org/dexpi/hasActuatingFunction", P]}]}]}
        result = compile_sparql(selection, index={"concepts": []})
        self.assertEqual(result["intent"], "relationship_lookup")
        self.assertIsNone(result["sparql"])
        self.assertEqual(result["status"], "requires_relationship_grounding")

    def test_requires_index(self):
        with self.assertRaisesRegex(ValueError, "schema index"):
            plan_relationship(QUESTION, None)

    def test_no_invented_predicates(self):
        index = {"concepts": [{"uri": P, "domain": "dexpi", "kind": "property"}]}
        with patch("semantic.dtwise_relationship_planner._traversals",
                   return_value=[{"complete_to_root": True,
                                  "property_chain": [P]}]):
            result = plan_relationship(QUESTION, index)
        self.assertIsNone(result["sparql"])
        self.assertEqual(result["ontology_evidence"], [])\n        self.assertIn("subject", result["reason"])

    def test_no_relationship_language_preserves_regular_lookup(self):
        self.assertFalse(is_relationship_question("ECAD device local identifier"))

    def test_other_relationship_terms(self):
        for term in ("connected", "linked", "related", "corresponding"):
            with self.subTest(term=term):
                self.assertTrue(is_relationship_question("devices " + term + " to reactor"))

    def test_roles_extracted_from_tep_question(self):
        result = plan_relationship(QUESTION, {"concepts": []})
        self.assertEqual(result["role_plan"]["subject"]["text"],
                         "the Tennessee Eastman Process reactor")
        self.assertEqual(result["role_plan"]["target"]["text"],
                         "process instruments")

    def test_instrument_matches_intermediate_shacl_edge(self):
        instrument_edge = "https://example.org/dexpi/hasInstrumentationFunction"
        leaf = "https://example.org/dexpi/hasAssetIdentifier"
        index = {"concepts": [{"uri": leaf, "domain": "dexpi", "kind": "property"}]}
        with patch("semantic.dtwise_relationship_planner._traversals",
                   return_value=[{"complete_to_root": True,
                                  "property_chain": [instrument_edge, leaf]}]):
            result = plan_relationship(QUESTION, index)
        self.assertEqual(result["role_evidence"]["target"][0]["uri"], leaf)
        self.assertEqual(result["role_evidence"]["target"][0]["match_scope"],
                         "shacl_path")
        self.assertIsNone(result["sparql"])

    def test_unverified_path_excluded(self):
        leaf = "https://example.org/dexpi/hasInstrumentationFunction"
        index = {"concepts": [{"uri": leaf, "domain": "dexpi", "kind": "property"}]}
        with patch("semantic.dtwise_relationship_planner._traversals",
                   return_value=[{"complete_to_root": False,
                                  "property_chain": [leaf]}]):
            result = plan_relationship(QUESTION, index)
        self.assertEqual(result["role_evidence"]["target"], [])

    def test_deterministic(self):
        index = {"concepts": []}
        self.assertEqual(plan_relationship(QUESTION, index),
                         plan_relationship(QUESTION, index))


if __name__ == "__main__":
    unittest.main()
