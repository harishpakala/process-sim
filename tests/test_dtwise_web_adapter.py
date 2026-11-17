"""Contract tests for the Web UI adapter to SHACL-validated Unified IR."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from process_sim.api import dtwise_query


QUESTION = "List OPCUAconnectivity SignalNames."
ENDPOINT = "http://localhost:7200/repositories/AAS"
SPARQL = "SELECT DISTINCT ?signal_name WHERE { ?s ?p ?signal_name }"


def sample_plan():
    return {
        "ir_version": "1.0",
        "entities": [{"alias": "signal", "domain": "opcua", "shape": "urn:signal-shape"}],
        "edges": [],
        "projections": [{"entity": "signal", "predicate": "urn:signalName",
                         "as": "signal_name"}],
        "filters": None,
        "operation": {"type": "select"},
        "return_entities": False,
    }


def sample_results():
    return {"results": {"bindings": [
        {"signal_name": {"type": "literal", "value": "Pressure"}}]}}


class DtwiseWebAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.schema = Path(self.tmp.name) / "schema.json"
        self.schema.write_text("{}", encoding="utf-8")
        self.env = {"GRAPHDB_SPARQL_ENDPOINT": ENDPOINT,
                    "DTWISE_UNIFIED_MODEL": "llama3.1:8b",
                    "OLLAMA_HOST": "http://localhost:11434"}

    def test_invokes_unified_ir_planner_compiler_and_executor(self):
        plan = sample_plan()
        with (patch.object(dtwise_query, "SCHEMA_PATH", self.schema),
              patch.object(dtwise_query, "generate_ir", return_value=plan) as generate,
              patch.object(dtwise_query, "compile_graph_ir", return_value=SPARQL) as compile_ir,
              patch.object(dtwise_query, "execute_select",
                           return_value=sample_results()) as execute):
            result = dtwise_query.run_question(" " + QUESTION + " ", environ=self.env)

        generate.assert_called_once_with(
            QUESTION, str(self.schema), model="llama3.1:8b",
            ollama_host="http://localhost:11434")
        compile_ir.assert_called_once_with(
            plan, str(self.schema), limit=100, graph_mode="all_named")
        execute.assert_called_once_with(SPARQL, ENDPOINT)
        self.assertEqual(result["mode"], "unified_ir_graphdb")
        self.assertTrue(result["executed"])
        self.assertEqual(result["answer"]["count"], 1)
        self.assertEqual(result["answer"]["values"], [{"value": "Pressure"}])
        self.assertEqual(result["question"], QUESTION)

    def test_rejects_invalid_question_without_execution(self):
        with patch.object(dtwise_query, "generate_ir") as generate:
            with self.assertRaises(ValueError):
                dtwise_query.run_question("no", environ=self.env)
        generate.assert_not_called()

    def test_missing_configuration_fails_closed(self):
        with patch.object(dtwise_query, "generate_ir") as generate:
            with self.assertRaises(dtwise_query.DtwiseUnavailable):
                dtwise_query.run_question(QUESTION, environ={})
        generate.assert_not_called()

    def test_missing_schema_fails_closed(self):
        with (patch.object(dtwise_query, "SCHEMA_PATH",
                           Path(self.tmp.name) / "missing.json"),
              patch.object(dtwise_query, "generate_ir") as generate):
            with self.assertRaises(dtwise_query.DtwiseUnavailable):
                dtwise_query.run_question(QUESTION, environ=self.env)
        generate.assert_not_called()

    def test_planner_rejection_is_not_replanned_or_executed(self):
        with (patch.object(dtwise_query, "SCHEMA_PATH", self.schema),
              patch.object(dtwise_query, "generate_ir",
                           side_effect=ValueError("SHACL evidence rejected")) as generate,
              patch.object(dtwise_query, "compile_graph_ir") as compile_ir,
              patch.object(dtwise_query, "execute_select") as execute):
            with self.assertRaisesRegex(dtwise_query.DtwiseRejected,
                                        "SHACL evidence rejected"):
                dtwise_query.run_question(
                    "List AssetIdentifiers shared by DEXPI and OPCUAConnectivity.",
                    environ=self.env)
        generate.assert_called_once()
        compile_ir.assert_not_called()
        execute.assert_not_called()

    def test_compiler_rejection_prevents_execution(self):
        with (patch.object(dtwise_query, "SCHEMA_PATH", self.schema),
              patch.object(dtwise_query, "generate_ir", return_value=sample_plan()),
              patch.object(dtwise_query, "compile_graph_ir",
                           side_effect=ValueError("Invalid graph")) as compile_ir,
              patch.object(dtwise_query, "execute_select") as execute):
            with self.assertRaisesRegex(dtwise_query.DtwiseRejected, "Invalid graph"):
                dtwise_query.run_question(QUESTION, environ=self.env)
        compile_ir.assert_called_once()
        execute.assert_not_called()

    def test_malformed_result_is_not_reported_as_success(self):
        malformed = {"results": {"bindings": [{}]}}
        with (patch.object(dtwise_query, "SCHEMA_PATH", self.schema),
              patch.object(dtwise_query, "generate_ir", return_value=sample_plan()),
              patch.object(dtwise_query, "compile_graph_ir", return_value=SPARQL),
              patch.object(dtwise_query, "execute_select",
                           return_value=malformed) as execute):
            with self.assertRaisesRegex(dtwise_query.DtwiseRejected,
                                        "Projected property missing"):
                dtwise_query.run_question(QUESTION, environ=self.env)
        execute.assert_called_once()

    def test_execution_failure_is_not_reported_as_success(self):
        # Current adapter propagates runtime/transport failures; it does not
        # convert them to DtwiseUnavailable. Assert the actual contract.
        with (patch.object(dtwise_query, "SCHEMA_PATH", self.schema),
              patch.object(dtwise_query, "generate_ir", return_value=sample_plan()),
              patch.object(dtwise_query, "compile_graph_ir", return_value=SPARQL),
              patch.object(dtwise_query, "execute_select",
                           side_effect=TimeoutError("GraphDB timed out")) as execute):
            with self.assertRaisesRegex(TimeoutError, "GraphDB timed out"):
                dtwise_query.run_question(QUESTION, environ=self.env)
        execute.assert_called_once_with(SPARQL, ENDPOINT)


if __name__ == "__main__":
    unittest.main()
