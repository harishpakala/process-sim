"""Offline contract tests; no Ollama or GraphDB required."""
import unittest

from process_sim.dtwise.semantic_selection_v2 import validate_semantic_selection_v2


class SemanticSelectionV2Tests(unittest.TestCase):
    def setUp(self):
        self.ids = {"path_ids": {"PATH_0"}, "property_ids": {"N0P0", "N0P1"},
                    "entity_ids": {"N0"}}
        self.selection = {
            "path_id": "PATH_0", "operation": "group_count",
            "projections": ["N0P0"], "group_by": ["N0P0"],
            "count_target": "N0",
            "aggregate_condition": {"operator": "gt", "value": 3},
            "filters": [],
        }

    def validate(self, value):
        return validate_semantic_selection_v2(value, **self.ids)

    def test_valid_grouped_count(self):
        self.assertEqual(self.validate(self.selection), self.selection)

    def test_reject_missing_path(self):
        selection = {**self.selection, "path_id": None}
        with self.assertRaisesRegex(ValueError, "evidence path"):
            self.validate(selection)

    def test_reject_total_count_as_grouped_count(self):
        selection = {**self.selection, "operation": "count",
                     "projections": [], "group_by": [],
                     "aggregate_condition": None}
        # A total count is structurally valid; semantic question coverage is a
        # separate validator responsibility, not guessed from this structure.
        self.assertEqual(self.validate(selection)["operation"], "count")

    def test_reject_aggregate_threshold_as_filter(self):
        selection = {**self.selection, "filters": [
            {"property": "N0P1", "op": "gt", "value": "3"}]}
        with self.assertRaisesRegex(ValueError, "property filter"):
            self.validate(selection)

    def test_reject_unevidenced_count_target(self):
        selection = {**self.selection, "count_target": "N99"}
        with self.assertRaisesRegex(ValueError, "count target"):
            self.validate(selection)

    def test_reject_mismatched_grouping_projection(self):
        selection = {**self.selection, "projections": ["N0P1"]}
        with self.assertRaisesRegex(ValueError, "grouping key"):
            self.validate(selection)

    def test_reject_boolean_aggregate_value(self):
        selection = {**self.selection,
                     "aggregate_condition": {"operator": "gt", "value": True}}
        with self.assertRaisesRegex(ValueError, "aggregate condition"):
            self.validate(selection)


if __name__ == "__main__":
    unittest.main()
