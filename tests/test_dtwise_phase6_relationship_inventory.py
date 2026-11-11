import unittest
from experiments.dtwise_phase6_relationship_inventory import inventory


class RelationshipInventoryTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"domains": [
            {"domain": "ecad", "source_file": "ecad.ttl", "node_shapes": [
                {"uri": "urn:source", "target_classes": ["urn:Source"],
                 "properties": [{"predicate": "urn:link", "kind": "object",
                                 "value_class": "urn:Target"}]},
                {"uri": "urn:target", "target_classes": ["urn:Target"],
                 "properties": [{"predicate": "urn:label", "kind": "datatype"}]},
            ]}], "cross_domain_identifier_candidates": []}

    def test_class_constraint_yields_candidate_not_verified_path(self):
        item = inventory(self.schema)["relationship_declarations"][0]
        self.assertEqual(item["target_shape_candidates"][0]["shape"], "urn:target")
        self.assertFalse(item["instance_triple_verified"])
        self.assertFalse(item["eligible_for_verified_traversal"])

    def test_absent_predicates_are_not_invented(self):
        report = inventory(self.schema)
        self.assertEqual(report["investigated_predicates"]
                         ["https://example.org/productcatalog/hasIRDI"], [])

    def test_no_class_constraint_is_unresolved(self):
        self.schema["domains"][0]["node_shapes"][0]["properties"][0].pop("value_class")
        item = inventory(self.schema)["relationship_declarations"][0]
        self.assertEqual(item["declaration_status"],
                         "object_property_without_shacl_target_class")

    def test_no_physical_membership_assertion(self):
        for item in inventory(self.schema)["relationship_declarations"]:
            self.assertFalse(item["physical_membership_verified"])


if __name__ == "__main__":
    unittest.main()
