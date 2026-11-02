import unittest
from process_sim.safsl.shacl.graphdb_revision import observe, verify_unchanged

INVENTORY = "https://example.org/graphs/assets"
CATALOG = "https://example.org/graphs/products"


class TestGraphDBRevision(unittest.TestCase):
    def setUp(self):
        self.assets = [{"asset": "urn:asset:1", "ref": "A-1"}]
        self.products = [{"product": "urn:product:1", "identifier": "A-1"}]

    def select(self, endpoint, query):
        return list(self.assets if "hasProductReference" in query else self.products)

    def observe(self):
        return observe("http://localhost:7200/repositories/AAS", INVENTORY, CATALOG,
                       complete=True, select_fn=self.select)

    def test_stable_fingerprints(self):
        first = self.observe()
        self.assertEqual(first.snapshot.assigned["urn:asset:1"], "A-1")
        self.assertTrue(verify_unchanged(first, "endpoint", INVENTORY, CATALOG,
                                         select_fn=self.select))

    def test_catalog_change_detected(self):
        first = self.observe()
        self.products.append({"product": "urn:product:2", "identifier": "A-1"})
        self.assertFalse(verify_unchanged(first, "endpoint", INVENTORY, CATALOG,
                                          select_fn=self.select))

    def test_inventory_change_detected(self):
        first = self.observe()
        self.assets[0] = {"asset": "urn:asset:1", "ref": "A-2"}
        self.assertFalse(verify_unchanged(first, "endpoint", INVENTORY, CATALOG,
                                          select_fn=self.select))

    def test_network_error_fails_closed(self):
        first = self.observe()
        def broken(*args):
            raise OSError("unavailable")
        self.assertFalse(verify_unchanged(first, "endpoint", INVENTORY, CATALOG,
                                          select_fn=broken))


if __name__ == "__main__":
    unittest.main()
