import unittest
from experiments.dtwise_phase6_grounding_diagnostics import diagnose


class GroundingDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "s0": {"properties": [{"predicate": "urn:valid"}]},
            "s1": {"properties": [{"predicate": "urn:other"}]},
            "s2": {"properties": [{"predicate": "urn:other"}]},
        }

    def test_selected_shape_is_valid(self):
        result = diagnose({"candidate_shapes": self.catalog, "plan": {
            "fields": [{"name": "x", "shape": "s0", "predicate": "urn:valid"}]}})
        self.assertEqual(result[0]["classification"], "valid_on_selected_shape")

    def test_alternative_shapes_not_automatically_selected(self):
        plan = {"fields": [{"name": "x", "shape": "s0", "predicate": "urn:other"}]}
        result = diagnose({"candidate_shapes": self.catalog, "plan": plan})
        self.assertEqual(result[0]["other_candidate_shapes"], ["s1", "s2"])
        self.assertEqual(result[0]["classification"], "declared_on_other_candidate_shape")
        self.assertEqual(plan["fields"][0]["shape"], "s0")
        self.assertFalse(result[0]["join_verified"])

    def test_absent_predicate_is_not_assumed_supported(self):
        result = diagnose({"candidate_shapes": self.catalog, "plan": {
            "fields": [{"name": "x", "shape": "s0", "predicate": "urn:missing"}]}})
        self.assertEqual(result[0]["classification"], "absent_from_candidate_schema")

    def test_filters_are_checked(self):
        result = diagnose({"candidate_shapes": self.catalog, "plan": {
            "fields": [], "filters": [{"shape": "s0", "predicate": "urn:other", "equals": "x"}]}})
        self.assertEqual(result[0]["section"], "filters")
        self.assertFalse(result[0]["declared_on_selected_shape"])

    def test_empty_audit(self):
        self.assertEqual(diagnose({}), [])


if __name__ == "__main__":
    unittest.main()
