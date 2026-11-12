"""Ontology-only multi-property planner contracts; no GraphDB or Ollama."""
import unittest

from semantic.dtwise_sparql_compiler import compile_sparql

NS = "https://example.org/ecad/"
PREFIX = [NS + "hasDevices", NS + "hasDevice"]
ASSET = NS + "hasAssetIdentifier"
LOCAL = NS + "hasLocalIdentifier"
OTHER = NS + "hasOtherValue"


def selected(question="Show ECAD devices and their asset identifiers",
             constraints=None, properties=(ASSET, LOCAL), prefixes=None):
    prefixes = prefixes or [PREFIX for _ in properties]
    return {
        "question": question, "intent": "lookup", "join_status": "unverified",
        "selected_concepts": [
            {"uri": uri, "domain": "ecad", "kind": "property",
             "paths": [{"property_chain": list(pre) + [uri],
                        "complete_to_root": True}]}
            for uri, pre in zip(properties, prefixes)],
        "value_constraints": [] if constraints is None else constraints,
    }


class MultiPropertyTests(unittest.TestCase):
    def test_common_entity_node_and_two_values(self):
        result = compile_sparql(selected())
        query = result["sparql"]
        self.assertIn("SELECT DISTINCT ?entity ?value1 ?value2", query)
        self.assertIn("?entity <" + ASSET + "> ?value1", query)
        self.assertIn("?entity <" + LOCAL + "> ?value2", query)
        self.assertEqual(result["common_entity_path"], PREFIX)
        self.assertEqual(result["execution_status"], "not_executed")

    def test_deterministic(self):
        selection = selected()
        self.assertEqual(compile_sparql(selection), compile_sparql(selection))

    def test_filter_on_one_selected_property(self):
        question = "Show ECAD device local identifiers where asset identifier equals X"
        selection = selected(question, [{"text": "X", "role": "hasAssetIdentifier"}])
        result = compile_sparql(selection)
        self.assertIn('FILTER(STR(?value1) = "X")', result["sparql"])
        self.assertEqual(result["value_filter"]["property"], ASSET)

    def test_second_property_filter(self):
        selection = selected("ECAD local identifier Y", [
            {"text": "Y", "role": "hasLocalIdentifier"}])
        self.assertIn('FILTER(STR(?value2) = "Y")',
                      compile_sparql(selection)["sparql"])

    def test_incompatible_entity_paths_rejected(self):
        selection = selected(prefixes=[
            PREFIX, [NS + "hasSymbols", NS + "hasSymbol"]])
        with self.assertRaisesRegex(ValueError, "common SHACL entity path"):
            compile_sparql(selection)

    def test_ambiguous_entity_paths_rejected(self):
        selection = selected()
        for concept in selection["selected_concepts"]:
            concept["paths"].append({
                "property_chain": [NS + "hasOtherCollection", NS + "hasOther",
                                   concept["uri"]],
                "complete_to_root": True})
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            compile_sparql(selection)

    def test_unverified_path_rejected(self):
        selection = selected()
        selection["selected_concepts"][1]["paths"][0]["complete_to_root"] = False
        with self.assertRaisesRegex(ValueError, "No complete grounded"):
            compile_sparql(selection)

    def test_cross_domain_rejected(self):
        selection = selected()
        selection["selected_concepts"][1]["domain"] = "dexpi"
        with self.assertRaisesRegex(ValueError, "Cross-domain"):
            compile_sparql(selection)

    def test_unknown_filter_role_rejected(self):
        selection = selected("ECAD X", [{"text": "X", "role": "hasUnknown"}])
        with self.assertRaisesRegex(ValueError, "uniquely match"):
            compile_sparql(selection)

    def test_invented_filter_value_rejected(self):
        selection = selected("ECAD devices", [
            {"text": "INVENTED", "role": "hasAssetIdentifier"}])
        with self.assertRaisesRegex(ValueError, "not present"):
            compile_sparql(selection)

    def test_multiple_filters_rejected(self):
        selection = selected("ECAD X Y", [
            {"text": "X", "role": "hasAssetIdentifier"},
            {"text": "Y", "role": "hasLocalIdentifier"}])
        with self.assertRaisesRegex(ValueError, "Only one"):
            compile_sparql(selection)

    def test_count_not_silently_converted_to_lookup(self):
        selection = selected()
        selection["intent"] = "count"
        with self.assertRaisesRegex(ValueError, "lookup only"):
            compile_sparql(selection)

    def test_duplicate_properties_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compile_sparql(selected(properties=(ASSET, ASSET)))

    def test_more_than_four_properties_rejected(self):
        with self.assertRaisesRegex(ValueError, "two to four"):
            compile_sparql(selected(properties=(ASSET, LOCAL, OTHER,
                                                NS + "hasFour", NS + "hasFive")))


if __name__ == "__main__":
    unittest.main()
