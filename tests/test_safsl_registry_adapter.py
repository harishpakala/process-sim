import unittest
from process_sim.safsl.shacl.compiler import CompilationError
from process_sim.safsl.shacl.registry_adapter import bindings_from_registry

A = "urn:example:aas:template:AssetInventory"
CLASS = "https://example.org/selira/Asset"
PATH = "https://example.org/selira/productRef"
REGISTRY = {"domains": [{
    "templateId": A,
    "instanceClasses": [CLASS],
    "templateClasses": [],
    "shaclPaths": [{"predicate": PATH}],
}]}


class TestRegistryAdapter(unittest.TestCase):
    def test_known_class_and_path(self):
        result = bindings_from_registry(REGISTRY, {
            A: {"class": CLASS, "fields": {"productRef": PATH}}
        })
        self.assertFalse(result["templates"][A]["complete"])

    def test_unknown_template_rejected(self):
        with self.assertRaises(CompilationError):
            bindings_from_registry(REGISTRY, {
                "urn:unknown": {"class": CLASS, "fields": {"productRef": PATH}}
            })

    def test_unknown_path_rejected(self):
        with self.assertRaises(CompilationError):
            bindings_from_registry(REGISTRY, {
                A: {"class": CLASS, "fields": {"productRef": "https://example.org/other"}}
            })


if __name__ == "__main__":
    unittest.main()
