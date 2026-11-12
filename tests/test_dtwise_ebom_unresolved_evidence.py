"""Tests for read-only unresolved EngineeringBOM evidence aggregation."""
import unittest

from semantic.dtwise_ebom_unresolved_evidence import QUERY, summarize


def binding(identifier, record, predicate, value):
    return {"assetIdentifier": {"value": identifier},
            "bomRecord": {"value": record},
            "predicate": {"value": predicate},
            "value": {"type": "literal", "value": value}}


class UnresolvedEvidenceTests(unittest.TestCase):
    def test_query_is_read_only_and_filters_unresolved(self):
        self.assertIn('"UNRESOLVED"', QUERY)
        self.assertIn("SELECT DISTINCT", QUERY)
        self.assertNotIn("DELETE", QUERY)
        self.assertNotIn("INSERT", QUERY)

    def test_preserves_properties_and_deduplicates_rows(self):
        rows = [binding("asset1", "record1", "urn:source", "ECAD"),
                binding("asset1", "record1", "urn:source", "ECAD"),
                binding("asset1", "record1", "urn:description", "example"),
                binding("asset2", "record2", "urn:source", "DEXPI")]
        report = summarize({"results": {"bindings": rows}})
        self.assertEqual(report["counts"], {"unresolved_records": 2,
                                            "asset_identifiers": 2})
        self.assertEqual(len(report["records"][0]["properties"]["urn:source"]), 1)
        self.assertEqual(report["semantic_approval"], "not_granted")

    def test_conflicting_identifier_fails_closed(self):
        with self.assertRaises(ValueError):
            summarize({"results": {"bindings": [
                binding("asset1", "record1", "urn:p", "x"),
                binding("asset2", "record1", "urn:p", "y")
            ]})

    def test_empty_evidence_is_not_approval(self):
        report = summarize({"results": {"bindings": []}})
        self.assertEqual(report["counts"]["unresolved_records"], 0)
        self.assertEqual(report["semantic_approval"], "not_granted")


if __name__ == "__main__":
    unittest.main()
