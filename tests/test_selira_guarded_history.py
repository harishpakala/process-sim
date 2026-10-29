"""Consumer-policy integration tests; all dependencies mocked."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from process_sim.selira import resolve_correspondence
from process_sim.selira.guarded_history import guarded_asset_history

RUN = "00000000-0000-4000-8000-000000000001"
REF = "opcua/XMEAS7"


def reviewed(status="validated", applicability="applicable"):
    return {
        "requestedProperty": "reactor_pressure",
        "signal": "XMEAS7", "reference": REF,
        "validationStatus": status,
        "applicabilityStatus": applicability,
        "evidenceReferences": ["urn:review:pi101"],
    }


def resolver(references, declarations):
    result = resolve_correspondence("reactor_pressure", references, declarations)
    return Mock(return_value=result)


class GuardedHistoryTests(unittest.TestCase):
    def run_case(self, references, declarations):
        reader = resolver(references, declarations)
        samples = Mock(return_value=[
            (1.0, 2700.0, datetime(2026, 10, 29, tzinfo=timezone.utc))
        ])
        result = guarded_asset_history(
            "https://example.org/assetinventory/PI_101", "reactor_pressure", RUN,
            declarations=declarations, correspondence_reader=reader,
            samples_reader=samples,
        )
        return result, samples

    def test_validated_mapping_fetches_samples(self):
        result, samples = self.run_case([REF], [reviewed()])
        self.assertTrue(result["authorized"])
        self.assertEqual(result["signal"], "XMEAS7")
        self.assertEqual(len(result["points"]), 1)
        samples.assert_called_once_with(RUN, "XMEAS7", 1000)

    def test_unverified_mapping_never_fetches_samples(self):
        result, samples = self.run_case([REF], [])
        self.assertFalse(result["authorized"])
        self.assertEqual(result["points"], [])
        samples.assert_not_called()

    def test_competing_mapping_never_fetches_samples(self):
        result, samples = self.run_case([REF, "opcua/XMEAS13"], [reviewed()])
        self.assertFalse(result["authorized"])
        samples.assert_not_called()

    def test_inapplicable_mapping_never_fetches_samples(self):
        result, samples = self.run_case([REF], [reviewed(applicability="inapplicable")])
        self.assertFalse(result["authorized"])
        samples.assert_not_called()

    def test_rejected_alternative_does_not_block_history(self):
        rejected = dict(reviewed(status="rejected"),
                        signal="XMEAS13", reference="opcua/XMEAS13")
        result, samples = self.run_case(
            [REF, "opcua/XMEAS13"], [reviewed(), rejected])
        self.assertTrue(result["authorized"])
        samples.assert_called_once()

    def test_invalid_limit_does_not_call_correspondence_reader(self):
        reader = Mock()
        with self.assertRaises(ValueError):
            guarded_asset_history("urn:asset", "reactor_pressure", RUN,
                                  limit=0, correspondence_reader=reader)
        reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
