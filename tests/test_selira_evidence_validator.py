"""Evidence validator tests: metadata consistency is not physical validation."""
import unittest

from process_sim.selira.evidence_validator import validate_pressure_correspondence


class EvidenceValidatorTests(unittest.TestCase):
    def test_three_documented_pressure_mappings_supported(self):
        for tag, prop, signal in (
            ("PI_101", "reactor_pressure", "XMEAS7"),
            ("PI_102", "separator_pressure", "XMEAS13"),
            ("PI_103", "stripper_pressure", "XMEAS16"),
        ):
            with self.subTest(tag=tag):
                result = validate_pressure_correspondence(tag, prop, signal)
                self.assertEqual(result.status, "supported_project_scope")
                self.assertEqual(result.checks["identity"], "match")
                self.assertEqual(result.checks["unit"], "match")
                self.assertEqual(result.checks["applicability"], "unknown")

    def test_wrong_signal_rejected_despite_same_pressure_unit(self):
        result = validate_pressure_correspondence(
            "PI_101", "reactor_pressure", "XMEAS13")
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.checks["identity"], "contradiction")

    def test_wrong_quantity_rejected(self):
        result = validate_pressure_correspondence(
            "PI_101", "separator_pressure", "XMEAS7")
        self.assertEqual(result.status, "rejected")

    def test_wrong_unit_rejected(self):
        result = validate_pressure_correspondence(
            "PI_101", "reactor_pressure", "XMEAS7", "deg C")
        self.assertEqual(result.status, "rejected")

    def test_unknown_asset_is_unresolved(self):
        result = validate_pressure_correspondence(
            "PI_999", "reactor_pressure", "XMEAS7")
        self.assertEqual(result.status, "unresolved")

    def test_unknown_version_is_unresolved(self):
        result = validate_pressure_correspondence(
            "PI_101", "reactor_pressure", "XMEAS7", scope_version="rev-2")
        self.assertEqual(result.status, "unresolved")

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            validate_pressure_correspondence("", "reactor_pressure", "XMEAS7")


if __name__ == "__main__":
    unittest.main()
