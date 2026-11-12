"""Offline integration baseline validator regression tests."""
import json
import unittest
from pathlib import Path

from semantic.dtwise_four_domain_baseline import BASELINE, validate_result


class FourDomainBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    def fixture(self):
        bindings = []
        for i in range(34):
            for j in range(2):
                row = {
                    "entity0": {"type": "uri", "value": f"urn:bom:{i}:{j}"},
                    "entity1": {"type": "uri", "value": f"urn:ecad:{i}"},
                    "entity2": {"type": "uri", "value": f"urn:dexpi:{i}"},
                    "entity3": {"type": "uri", "value": f"urn:inventory:{i}"},
                }
                for k in range(4):
                    row[f"id{k}"] = {"type": "literal", "value": f"urn:asset:{i}"}
                bindings.append(row)
        return {"results": {"bindings": bindings}}

    def test_valid_baseline(self):
        actual, failures = validate_result(self.fixture(), self.baseline)
        self.assertFalse(failures)
        self.assertEqual(actual["rows"], 68)

    def test_missing_row_fails(self):
        document = self.fixture()
        document["results"]["bindings"].pop()
        _, failures = validate_result(document, self.baseline)
        self.assertTrue(failures)

    def test_identifier_mismatch_fails(self):
        document = self.fixture()
        document["results"]["bindings"][0]["id3"]["value"] = "urn:other"
        _, failures = validate_result(document, self.baseline)
        self.assertTrue(any("identifiers differ" in failure for failure in failures))

    def test_duplicate_row_fails(self):
        document = self.fixture()
        document["results"]["bindings"][1] = document["results"]["bindings"][0]
        _, failures = validate_result(document, self.baseline)
        self.assertTrue(any("duplicate" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
