"""Created: 2026-10-23
Author: Harish"""

import unittest
from process_sim.ai.property_alignment import validate_alignment, assess_alignments

PROPERTY = "https://example.org/spec/pressure"
IRDI = "0173-1#02-TEST001#001"

def declaration(status="verified"):
    return {"catalogPropertyIri": PROPERTY, "catalogPropertyTermIrdi": IRDI,
            "signal": "XMEAS7", "measuredQuantityTermIrdi": "0173-1#02-TEST002#001",
            "unit": "kPa", "evidenceReference": "https://example.org/evidence/7",
            "verificationStatus": status, "applicability": "reviewed engineering mapping"}

class AlignmentTests(unittest.TestCase):
    def test_no_semantic_reference_means_no_alignment(self):
        props = [{"iri": PROPERTY, "semanticIds": [], "supplementalSemanticIds": []}]
        result = assess_alignments(props, "XMEAS7", [declaration()])
        self.assertEqual(result[0]["status"], "unverified")
        self.assertFalse(result[0]["comparisonAuthorized"])

    def test_explicit_verified_alignment_still_does_not_authorize_comparison(self):
        props = [{"iri": PROPERTY, "semanticIds": [IRDI], "supplementalSemanticIds": []}]
        result = assess_alignments(props, "XMEAS7", [declaration()])
        self.assertEqual(result[0]["status"], "verified_alignment")
        self.assertFalse(result[0]["comparisonAuthorized"])
        self.assertEqual(result[0]["evidence"][0]["evidenceReference"],
                         "https://example.org/evidence/7")

    def test_proposed_not_verified(self):
        props = [{"iri": PROPERTY, "semanticIds": [IRDI], "supplementalSemanticIds": []}]
        self.assertEqual(assess_alignments(props, "XMEAS7", [declaration("proposed")])[0]["status"],
                         "unverified")

    def test_invalid_declaration_rejected(self):
        bad = declaration()
        bad["evidenceReference"] = "unverified"
        with self.assertRaises(ValueError):
            validate_alignment(bad)
