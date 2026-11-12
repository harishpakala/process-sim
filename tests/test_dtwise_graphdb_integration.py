"""Offline tests for the optional live GraphDB integration runner."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic import dtwise_graphdb_integration as integration


class GraphDBIntegrationTests(unittest.TestCase):
    def test_invalid_endpoint_fails_closed(self):
        with self.assertRaises(ValueError):
            integration.execute("not-an-endpoint", "SELECT * WHERE {}")

    def test_runner_compiles_executes_and_validates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in (
                ("index.json", {"concepts": []}),
                ("catalog.json", {"mappings": []}),
                ("baseline.json", {
                    "mapping_status": "candidate_pending_semantic_approval",
                    "expected": {"rows": 0, "shared_identifiers": 0,
                                 "engineeringbom_records": 0, "ecad_devices": 0,
                                 "dexpi_objects": 0, "assetinventory_assets": 0},
                    "columns": {"entities": ["entity0", "entity1", "entity2", "entity3"],
                                "identifiers": ["id0", "id1", "id2", "id3"]}
                }),
            ):
                (root / name).write_text(json.dumps(data), encoding="utf-8")
            with patch.object(integration, "compile_cross_domain",
                              return_value={"sparql": "SELECT DISTINCT ?x WHERE {}"}) as compile_mock, \
                 patch.object(integration, "execute",
                              return_value={"results": {"bindings": []}}) as execute_mock:
                result = integration.run("http://localhost:7200/repositories/test",
                                         root / "index.json", root / "catalog.json",
                                         root / "baseline.json")
            self.assertTrue(result["passed"])
            self.assertEqual(result["mapping_status"], "candidate_pending_semantic_approval")
            self.assertTrue(compile_mock.call_args.kwargs["allow_candidate"])
            execute_mock.assert_called_once()
            self.assertIn("SELECT DISTINCT", execute_mock.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
