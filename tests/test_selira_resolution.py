"""Offline SELiRA correspondence tests; no GraphDB or TimescaleDB required."""
import unittest

from process_sim.selira import authorize_use, resolve_correspondence

REF = "opcua/XMEAS7"
PROPERTY = "reactor_pressure"


def declaration(reference=REF, signal="XMEAS7", status="validated",
                applicability="applicable", evidence=("urn:review:pi101",)):
    return {
        "requestedProperty": PROPERTY, "signal": signal,
        "reference": reference, "validationStatus": status,
        "applicabilityStatus": applicability, "evidenceReferences": list(evidence),
    }


class ResolutionTests(unittest.TestCase):
    def test_validated_declaration(self):
        result = resolve_correspondence(PROPERTY, [REF], [declaration()])
        self.assertEqual(result.resolution_status, "validated")
        self.assertEqual(result.selected_signal, "XMEAS7")
        self.assertTrue(authorize_use(result))

    def test_unique_reference_is_not_automatically_validated(self):
        result = resolve_correspondence(PROPERTY, [REF])
        self.assertEqual(result.resolution_status, "unresolved")
        self.assertFalse(authorize_use(result))

    def test_missing_reference(self):
        self.assertEqual(resolve_correspondence(PROPERTY, []).resolution_status,
                         "unresolved")

    def test_ambiguous_signals_even_with_one_verified(self):
        result = resolve_correspondence(PROPERTY, [REF, "opcua/XMEAS13"],
                                        [declaration()])
        self.assertEqual(result.resolution_status, "ambiguous")
        self.assertFalse(authorize_use(result))

    def test_inapplicable(self):
        result = resolve_correspondence(
            PROPERTY, [REF], [declaration(applicability="inapplicable")])
        self.assertFalse(authorize_use(result))
        self.assertEqual(result.resolution_status, "unresolved")

    def test_conflicting_declarations(self):
        result = resolve_correspondence(
            PROPERTY, [REF], [declaration(), declaration(status="rejected")])
        self.assertEqual(result.resolution_status, "unresolved")
        self.assertEqual(result.candidates[0].reason, "conflicting declarations")

    def test_rejected_candidate_is_not_authorized_alone(self):
        result = resolve_correspondence(
            PROPERTY, [REF], [declaration(status="rejected")])
        self.assertEqual(result.resolution_status, "unresolved")
        self.assertFalse(authorize_use(result))

    def test_unverified_competitor_still_blocks_authorization(self):
        result = resolve_correspondence(
            PROPERTY, [REF, "opcua/XMEAS13"], [declaration()])
        self.assertEqual(result.resolution_status, "ambiguous")
        self.assertFalse(authorize_use(result))

    def test_validated_requires_evidence(self):
        with self.assertRaises(ValueError):
            resolve_correspondence(PROPERTY, [REF], [declaration(evidence=())])

    def test_reference_signal_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            resolve_correspondence(PROPERTY, [REF],
                                   [declaration(signal="XMEAS8")])

    def test_rejected_candidate_does_not_block_validated_candidate(self):
        result = resolve_correspondence(
            PROPERTY, [REF, "opcua/XMEAS13"],
            [declaration(), declaration(reference="opcua/XMEAS13",
                                        signal="XMEAS13", status="rejected")])
        self.assertTrue(authorize_use(result))


if __name__ == "__main__":
    unittest.main()
