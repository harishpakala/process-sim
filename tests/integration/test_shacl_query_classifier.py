"""Offline contract tests: routing depends on extracted structure, not schema names."""
import unittest

from process_sim.dtwise.experimental_shacl_query_classifier import (
    operation_from_intent, validate_intent,
)


def intent(results, filters=(), owner=None, boolean=None, explicit=True, action="retrieve"):
    return dict(action=action, results=list(results), shared_owner=owner,
                filters=[dict(property=f"Owner.field{i}", operator="=", value=f"v{i}")
                         for i in range(len(filters))],
                boolean_operator=boolean, explicit_filter_syntax=explicit)


class QueryClassificationTests(unittest.TestCase):
    def test_operation_mapping_uses_structure_not_entity_names(self):
        examples = [
            (intent(["Thing.value"]), "phase1-plan"),
            (intent(["Thing.value"], [1]), "phase2-filter"),
            (intent(["Thing.value"], [1, 2], boolean="AND"), "phase3-and"),
            (intent(["A.value", "B.value"], owner="Root"), "phase4-join"),
            (intent(["A.value", "B.value"], [1], owner="Root"), "phase4-filtered-join"),
            (intent(["A.value", "B.value"], [1, 2], owner="Root", boolean="OR"), "phase4-and-join"),
            (intent(["A.value", "B.value"], [1, 2], owner="Root", boolean="AND", explicit=False), "direct-intent"),
            (intent(["Thing.value"], action="aggregate"), None),
        ]
        for value, expected in examples:
            with self.subTest(expected=expected):
                result = operation_from_intent(value)
                self.assertEqual(result["operation"], expected)

    def test_malformed_intent_rejected(self):
        with self.assertRaises(ValueError):
            validate_intent('{"action":"retrieve"}')

    def test_unsupported_operator(self):
        value = intent(["Thing.value"], [1])
        value["filters"][0]["operator"] = ">"
        self.assertEqual(operation_from_intent(value)["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
