"""Offline regression tests for EngineeringBOM association-quality reporting."""
import unittest

from semantic.dtwise_ebom_association_quality import FUNCTIONAL, UNRESOLVED, assess


def row(identifier, record, basis, revision="UNSPECIFIED"):
    values = {
        "assetIdentifier": identifier, "bomRecord": record,
        "bomItemId": record, "engineeringLocalId": record,
        "revision": revision, "associationBasis": basis,
    }
    return {key: {"type": "literal", "value": value} for key, value in values.items()}


class AssociationQualityTests(unittest.TestCase):
    def test_classifies_pairs_without_semantic_promotion(self):
        document = {"results": {"bindings": [
            row("a", "r1", FUNCTIONAL), row("a", "r2", FUNCTIONAL),
            row("b", "r3", UNRESOLVED), row("b", "r4", UNRESOLVED),
            row("c", "r5", FUNCTIONAL), row("c", "r6", UNRESOLVED),
        ]}}
        result = assess(document)
        self.assertEqual(result["counts"]["rows"], 6)
        self.assertEqual(result["identifier_groups"], {
            "both_functional_not_physical": 1, "both_unresolved": 1,
            "mixed_functional_unresolved": 1,
        })
        self.assertFalse(result["semantic_confirmation_assessed"])
        self.assertEqual(result["semantically_confirmed_asset_relationships"], 0)

    def test_missing_optional_evidence_is_not_confirmed(self):
        item = row("a", "r1", FUNCTIONAL)
        del item["associationBasis"]
        result = assess({"results": {"bindings": [item]}})
        self.assertEqual(result["association_basis"]["MISSING"], 1)
        self.assertEqual(result["missing_fields"]["associationBasis"], 1)
        self.assertEqual(result["identifier_groups"]["other_multiplicity"], 1)

    def test_missing_identifier_fails_closed(self):
        item = row("a", "r1", UNRESOLVED)
        del item["assetIdentifier"]
        with self.assertRaises(ValueError):
            assess({"results": {"bindings": [item]}})

    def test_unknown_basis_remains_unknown(self):
        result = assess({"results": {"bindings": [
            row("a", "r1", "OTHER"), row("a", "r2", "OTHER")
        ]}})
        self.assertEqual(result["identifier_groups"]["other_or_unknown"], 1)
        self.assertEqual(result["association_basis"]["OTHER"], 2)


if __name__ == "__main__":
    unittest.main()
