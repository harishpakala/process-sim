"""Offline tests for GraphDB-backed asset specification query."""
import io
import json
import unittest
from unittest.mock import patch
from process_sim.api.asset_specifications import asset_specifications


class FakeResponse:
    def __init__(self, bindings):
        self.payload = json.dumps({"results": {"bindings": bindings}}).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.payload


def binding(**fields):
    return {key: {"type": "literal", "value": value}
            for key, value in fields.items()}


class AssetSpecificationsTests(unittest.TestCase):
    @patch("process_sim.api.asset_specifications.urlopen")
    def test_linked_product_and_specifications(self, fetch):
        fetch.return_value = FakeResponse([
            binding(asset="urn:asset", name="Sensor", productReference="urn:product",
                    product="urn:catalog-product", manufacturer="SMC",
                    spec="urn:spec", specName="ProofPressure", specValue="500 kPa"),
            binding(asset="urn:asset", name="Sensor", productReference="urn:product",
                    product="urn:catalog-product", manufacturer="SMC",
                    spec="urn:spec", specName="ProofPressure", specValue="500 kPa"),
        ])
        result = asset_specifications("urn:asset", "http://localhost:7200/repositories/AAS")
        self.assertEqual(result["linkStatus"], "linked")
        self.assertEqual(len(result["technicalSpecifications"]), 1)
        self.assertEqual(result["technicalSpecifications"][0]["value"], "500 kPa")
        self.assertEqual(result["technicalSpecifications"][0]["verificationStatus"], "unverified")

    @patch("process_sim.api.asset_specifications.urlopen")
    def test_missing_catalog_product_is_not_invented(self, fetch):
        fetch.return_value = FakeResponse([binding(asset="urn:asset",
                                                   productReference="urn:missing")])
        result = asset_specifications("urn:asset", "http://localhost:7200/repositories/AAS")
        self.assertIsNone(result["product"])
        self.assertEqual(result["linkStatus"], "unresolved")

    def test_rejects_untrusted_query_fragments(self):
        with self.assertRaises(ValueError):
            asset_specifications('x" } UNION { ?s ?p ?o', "http://localhost")


if __name__ == "__main__":
    unittest.main()
