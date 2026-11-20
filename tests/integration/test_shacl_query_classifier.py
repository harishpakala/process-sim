"""Offline regression tests for deterministic, schema-name-independent routing."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_shacl_query_classifier import classify_single_domain_query
from run_shacl_planner import CASES


class QueryClassificationTests(unittest.TestCase):
    def test_all_existing_single_domain_categories(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                actual = classify_single_domain_query(case["question"])
                self.assertEqual(actual["operation"], case["mode"].removeprefix("--"))

    def test_generic_renamed_shapes(self):
        cases = {
            "Show Value of Item belonging to Root": "phase1-plan",
            "Show Value of Item belonging to Root where Root Code = X1": "phase2-filter",
            "Show Value of Item belonging to Root where Root Code = X1 and Root Type = Y2": "phase3-and",
            "Show Item Value and OtherItem Value belonging to the same Root": "phase4-join",
            "Show Item Value and OtherItem Value belonging to the same Root where Root Code = X1": "phase4-filtered-join",
            "Show Item Value and OtherItem Value belonging to the same Root where Root Code = X1 or Root Type = Y2": "phase4-and-join",
            "Find the values of Item and OtherItem for roots with Code X1 and Type Y2": "direct-intent",
        }
        for question, operation in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classify_single_domain_query(question)["operation"], operation)

    def test_unsupported_does_not_guess(self):
        for question in ("Count devices", "Show Address where Code > 10",
                         "Show Address where Code = X or Type = Y"):
            with self.subTest(question=question):
                self.assertEqual(classify_single_domain_query(question)["status"], "unsupported")

    def test_no_ollama_call(self):
        with patch("process_sim.dtwise.experimental_shacl_ollama.ollama_select",
                   side_effect=AssertionError("Ollama must not be called")):
            self.assertEqual(classify_single_domain_query("Show Address")["operation"], "phase1-plan")


if __name__ == "__main__":
    unittest.main()
