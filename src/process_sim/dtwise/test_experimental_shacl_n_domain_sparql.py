"""Offline regression tests for experimental deterministic N-domain SPARQL."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_sparql import compile_n_domain_sparql
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


class TestNDomainSparql(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[3]
        cls.schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
        cls.mappings = load_cross_domain_mappings(root / "semantic/ontology2/dtwise/cross-domain-mappings.json")

    def plan(self, outputs):
        domains = ("dexpi", "ecad", "assetinventory")
        question = ("Return only DEXPI Equipment whose AssetIdentifier matches "
                    "ECAD Device and AssetInventory Asset.")
        prepared = prepare_live_candidates(self.schema, self.mappings, question, domains)
        prompt = prepared["prompt"]
        owners = {"dexpi": "Equipment", "ecad": "Device", "assetinventory": "Asset"}
        ids = {}
        results = {}
        for domain, owner in owners.items():
            choices = [p for p in prompt["identifier_path_candidates"]
                       if p["domain"] == domain and p["path"] == owner + " → AssetIdentifier"]
            self.assertEqual(len(choices), 1)
            ids[domain] = choices[0]["id"]
            matches = [r for r in prompt["result_candidates"]
                       if r["domain"] == domain and r["kind"] == "result" and r["path"] == owner]
            self.assertEqual(len(matches), 1)
            results[domain] = matches[0]["id"]
        edges = [edge["id"] for edge in prompt["mapping_candidates"]
                 if {edge["left_domain"], edge["right_domain"]} in (
                     {"dexpi", "ecad"}, {"dexpi", "assetinventory"},
                     {"ecad", "assetinventory"})]
        self.assertEqual(len(edges), 3)
        selection = {
            "status": "selected",
            "result_ids": [results[d] for d in outputs],
            "identifier_path_ids": list(ids.values()),
            "mapping_ids": edges,
            "reason": "Explicit fixture selection",
        }
        return selection, prepared

    def test_single_projection_and_all_approved_joins(self):
        selection, prepared = self.plan(("dexpi",))
        query = compile_n_domain_sparql(selection, prepared)
        self.assertTrue(query.startswith("SELECT DISTINCT ?n"))
        self.assertEqual(query.count("FILTER("), 3)
        self.assertIn("<https://example.org/dexpi/hasAssetIdentifier>", query)
        self.assertIn("<https://example.org/ecad/hasAssetIdentifier>", query)
        self.assertIn("<https://example.org/assetinventory/hasAssetIdentifier>", query)
        self.assertNotIn("rdf:type", query)
        self.assertNotIn("NodeShape", query)

    def test_two_projected_entities(self):
        selection, prepared = self.plan(("assetinventory", "ecad"))
        query = compile_n_domain_sparql(selection, prepared)
        self.assertEqual(len(query.split(" WHERE {")[0].split()) - 2, 2)
        self.assertEqual(query.count("FILTER("), 3)

    def test_ambiguous_cannot_compile(self):
        _, prepared = self.plan(("dexpi",))
        with self.assertRaises(SelectionContractError):
            compile_n_domain_sparql({
                "status": "ambiguous", "result_ids": [],
                "identifier_path_ids": [], "mapping_ids": [],
                "reason": "Not enough information",
            }, prepared)

    def test_unapproved_mapping_rejected(self):
        selection, prepared = self.plan(("dexpi",))
        selection["mapping_ids"] = ["invented-mapping"]
        with self.assertRaises(SelectionContractError):
            compile_n_domain_sparql(selection, prepared)


if __name__ == "__main__":
    unittest.main()
