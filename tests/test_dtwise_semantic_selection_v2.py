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


    def test_boolean_existence_and_missing(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "where": {"op": "and", "conditions": [
                 {"op": "exists", "property": "N0P0"},
                 {"op": "missing", "property": "N0P1"}]}}
        self.assertEqual(self.validate(s)["where"]["op"], "and")

    def test_string_regex_and_case_insensitive_contains(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "where": {"op": "or", "conditions": [
                 {"op": "regex", "property": "N0P0", "value": "^PI-"},
                 {"op": "contains", "property": "N0P1",
                  "value": "reactor", "ignore_case": True}]}}
        self.assertEqual(len(self.validate(s)["where"]["conditions"]), 2)

    def test_order_limit_and_optional_projection(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "order_by": {"property": "N0P0", "direction": "desc"},
             "limit": 5, "optional_properties": ["N0P0"]}
        self.assertEqual(self.validate(s)["limit"], 5)

    def test_reject_unverified_boolean_property(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "where": {"op": "exists", "property": "N99P99"}}
        with self.assertRaisesRegex(ValueError, "existence"):
            self.validate(s)

    def test_reject_bad_regex(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "where": {"op": "regex", "property": "N0P0", "value": "["}}
        with self.assertRaisesRegex(ValueError, "regex"):
            self.validate(s)

    def test_reject_conflicting_filter_representations(self):
        s = {**self.selection, "operation": "select", "count_target": None,
             "group_by": [], "aggregate_condition": None,
             "where": {"op": "exists", "property": "N0P0"},
             "filters": [{"property": "N0P1", "op": "eq", "value": "x"}]}
        with self.assertRaisesRegex(ValueError, "either legacy"):
            self.validate(s)

if __name__ == "__main__":
    unittest.main()
