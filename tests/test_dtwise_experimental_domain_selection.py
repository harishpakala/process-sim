"""Tests for LLM-first domain-wide regex evidence selection."""
import json
import unittest

from process_sim.dtwise.experimental_domain_selection import select_domain_regex_plan


class DomainRegexSelectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"entities": [
            {"domain": "ECAD", "shape": "urn:Device",
             "properties": ["urn:hasLocalId", "urn:hasName"]},
            {"domain": "ECAD", "shape": "urn:Instrument",
             "properties": ["urn:hasLocalId"]},
            {"domain": "DEXPI", "shape": "urn:Device",
             "properties": ["urn:hasLocalId"]}]}

    def select(self, question, choice):
        requests = []
        def request(url, payload, timeout):
            requests.append(payload)
            return {"message": {"content": json.dumps(choice)}}
        result = select_domain_regex_plan(
            question, self.catalog, model="mock", request_json=request,
            ollama_host="http://localhost", timeout=1)
        return result, requests

    def test_domain_regex_uses_all_evidenced_property_owners(self):
        result, requests = self.select(
            "Which ECAD entities have a LocalId matching the regular expression ^PI-?",
            {"operation": "regex", "property_id": "P0", "pattern": "^PI-"})
        plan, selection = result
        self.assertEqual(plan["domain_regex"]["domain"], "ECAD")
        self.assertEqual(plan["domain_regex"]["pattern"], "^PI-")
        self.assertEqual(len(plan["domain_regex"]["paths"]), 2)
        self.assertEqual(len(requests[0]["messages"][1]["content"]) < 1000, True)

    def test_invented_property_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invented domain property"):
            self.select("ECAD LocalId matches ^PI-", {
                "operation": "regex", "property_id": "P99", "pattern": "^PI-"})

    def test_modified_regex_is_grounded_to_question(self):
        result, _ = self.select(
            "ECAD LocalId matching the regular expression ^PI-?",
            {"operation": "regex", "property_id": "P0", "pattern": "PI-"})
        self.assertEqual(result[0]["domain_regex"]["pattern"], "^PI-")

    def test_regex_requires_explicit_expression(self):
        with self.assertRaisesRegex(ValueError, "explicit regular expression"):
            self.select("ECAD LocalId matches PI-", {
                "operation": "regex", "property_id": "P0", "pattern": "PI-"})

    def test_two_required_properties_across_domain(self):
        result, _ = self.select(
            "Which ECAD entities have both LocalId and Name?",
            {"operation": "has_all_properties", "property_id": None,
             "property_ids": ["P0", "P1"], "pattern": None})
        plan, selection = result
        self.assertEqual(plan["domain_both_properties"]["domain"], "ECAD")
        self.assertEqual(set(plan["domain_both_properties"]["properties"]),
                         {"LocalId", "Name"})
        self.assertEqual(selection["choice"], "VERIFIED_LLM_DOMAIN_ALL_PROPERTIES")

    def test_two_properties_requires_conjunction(self):
        with self.assertRaisesRegex(ValueError, "Unrequested all-properties"):
            self.select("Show ECAD LocalId and Name", {
                "operation": "has_all_properties", "property_id": None,
                "property_ids": ["P0", "P1"], "pattern": None})

    def test_unsupported_returns_none(self):
        result, _ = self.select("Count ECAD LocalId", {
            "operation": "unsupported", "property_id": None, "pattern": None})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
