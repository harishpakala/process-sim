"""Offline checks using the actual DEXPI and ECAD template lifting pipeline."""

# Created: 2026-10-23
# Author: Harish
import unittest

from process_sim.ai.shacl_registry import build_shacl_registry, planner_shacl_context
from semantic.config import TARGETS


class ShaclRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_shacl_registry(targets=[
            target for target in TARGETS if target[0] in ("dexpi", "ecad")
        ])

    def test_both_domains_have_lifted_shapes(self):
        domains = {d["domain"]: d for d in self.registry["domains"]}
        self.assertEqual(set(domains), {"dexpi", "ecad"})
        for domain in domains.values():
            self.assertGreater(domain["shapeCount"], 0)
            self.assertGreater(len(domain["shaclPaths"]), 0)
            self.assertGreater(domain["tripleCount"], 0)

    def test_dexpi_identifier_constraint_from_template(self):
        dexpi = next(d for d in self.registry["domains"] if d["domain"] == "dexpi")
        paths = [p for p in dexpi["shaclPaths"]
                 if p["predicate"] == "https://example.org/dexpi/hasAssetIdentifier"]
        self.assertTrue(paths)
        self.assertTrue(any(p["minCount"] == "1" and p["maxCount"] == "1" for p in paths))

    def test_dexpi_instance_concept(self):
        dexpi = next(d for d in self.registry["domains"] if d["domain"] == "dexpi")
        self.assertIn("https://example.org/dexpi/Equipment", dexpi["instanceClasses"])
        self.assertTrue(any(p["iri"] == "https://example.org/dexpi/hasEquipment"
                            for p in dexpi["predicates"]))

    def test_scoping_and_explicit_budget(self):
        scoped = planner_shacl_context(self.registry, domains=["dexpi"], max_paths=10000)
        self.assertEqual([d["domain"] for d in scoped["domains"]], ["dexpi"])
        with self.assertRaises(ValueError):
            planner_shacl_context(self.registry, max_paths=0)
        with self.assertRaises(ValueError):
            planner_shacl_context(self.registry, domains=["unknown"])


if __name__ == "__main__":
    unittest.main()
