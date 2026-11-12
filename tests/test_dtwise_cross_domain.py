"""Regression tests for deterministic evidence-gated cross-domain SPARQL.

Run: python -m unittest discover -s tests -p 'test_dtwise_cross_domain.py' -v
No Ollama or GraphDB connection is required.
"""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic.dtwise_cross_domain import _validate_path, compile_cross_domain

CATALOG_PATH = (Path(__file__).resolve().parents[1] / "semantic" / "ontology" /
                "dtwise" / "cross-domain-mappings.json")
QUESTION_3 = "Which EngineeringBOM items correspond to ECAD devices and DEXPI objects?"
QUESTION_2 = "Which EngineeringBOM items correspond to ECAD devices?"


class CrossDomainRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def compile(self, question=QUESTION_3, catalog=None, allow_candidate=True):
        # Unit tests isolate query construction from SHACL graph reconstruction.
        # SHACL enforcement is tested separately with real _validate_path calls.
        with patch("semantic.dtwise_cross_domain._validate_path"):
            return compile_cross_domain(
                question, {}, self.catalog if catalog is None else catalog,
                allow_candidate=allow_candidate)

    def test_three_domain_entity_to_identifier_edges_are_connected(self):
        query = self.compile()["sparql"]
        for entity, predicate, identifier in (
            ("?bomRecord", "engineeringbom", "?assetId"),
            ("?device", "ecad", "?ecadId"),
            ("?dexpiObject", "dexpi", "?dexpiId"),
        ):
            triple = (entity + " <https://example.org/" + predicate +
                      "/hasAssetIdentifier> " + identifier + " .")
            self.assertIn(triple, query)
        for disconnected in ("?eb2 <https://example.org/engineeringbom/hasAssetIdentifier>",
                             "?ec2 <https://example.org/ecad/hasAssetIdentifier>",
                             "?dx02 <https://example.org/dexpi/hasAssetIdentifier>"):
            self.assertNotIn(disconnected, query)

    def test_dexpi_union_covers_all_three_cataloged_categories(self):
        query = self.compile()["sparql"]
        self.assertEqual(query.count("UNION"), 2)
        for plural, singular in (
            ("hasActuatingFunctions", "hasActuatingFunction"),
            ("hasEquipments", "hasEquipment"),
            ("hasInstrumentationFunctions", "hasInstrumentationFunction"),
        ):
            self.assertIn("/" + plural + ">", query)
            self.assertIn("/" + singular + ">", query)
        self.assertEqual(query.count(
            "?dexpiObject <https://example.org/dexpi/hasAssetIdentifier> ?dexpiId ."), 3)

    def test_filters_and_result_projection(self):
        result = self.compile()
        self.assertIn("SELECT DISTINCT ?assetId ?bomRecord ?device ?dexpiObject", result["sparql"])
        self.assertIn("FILTER(STR(?assetId) = STR(?ecadId))", result["sparql"])
        self.assertIn("FILTER(STR(?assetId) = STR(?dexpiId))", result["sparql"])
        self.assertEqual(result["execution_status"], "not_executed")
        self.assertEqual(result["cross_domain_join"], "candidate")

    def test_candidate_requires_explicit_opt_in_for_both_domain_counts(self):
        for question in (QUESTION_2, QUESTION_3):
            with self.subTest(question=question):
                with self.assertRaisesRegex(ValueError, "not semantically approved"):
                    self.compile(question, allow_candidate=False)

    def test_two_domain_query_is_still_supported(self):
        result = self.compile(QUESTION_2)
        query = result["sparql"]
        self.assertEqual(result["mapping_id"], "engineeringbom_ecad_asset_identifier")
        self.assertIn("FILTER(STR(?ebomId) = STR(?ecadId))", query)
        self.assertNotIn("UNION", query)
        self.assertIn("?eb2 <https://example.org/engineeringbom/hasAssetIdentifier> ?ebomId", query)

    def test_invalid_shacl_path_is_rejected(self):
        # No indexed shape evidence: never accept a catalog path solely by its URI.
        path = self.catalog["three_domain_mappings"][0]["dexpi_paths"][0]
        with self.assertRaisesRegex(ValueError, "not grounded in SHACL"):
            _validate_path({"shape_paths": [], "relationships": []}, "dexpi", path)

    def test_wrong_domain_namespace_is_rejected(self):
        path = self.catalog["three_domain_mappings"][0]["dexpi_paths"][0]
        with self.assertRaisesRegex(ValueError, "unexpected namespace"):
            _validate_path({}, "ecad", path)

    def test_missing_three_domain_mapping_fails_closed(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["three_domain_mappings"] = []
        with self.assertRaisesRegex(ValueError, "No unique explicit three-domain mapping"):
            self.compile(catalog=catalog)

    def test_duplicate_dexpi_path_fails_closed(self):
        catalog = copy.deepcopy(self.catalog)
        paths = catalog["three_domain_mappings"][0]["dexpi_paths"]
        paths.append(list(paths[0]))
        with self.assertRaisesRegex(ValueError, "missing or duplicated"):
            self.compile(catalog=catalog)

    def test_unsupported_comparison_fails_closed(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["three_domain_mappings"][0]["comparison"] = "approximate"
        with self.assertRaisesRegex(ValueError, "Unsupported join comparison"):
            self.compile(catalog=catalog)

    def test_invalid_limit_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "LIMIT"):
            compile_cross_domain(QUESTION_3, {}, self.catalog,
                                 allow_candidate=True, limit=0)


if __name__ == "__main__":
    unittest.main()
