"""Contract tests for the Web UI adapter to the unchanged DTwise CLI."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from process_sim.api import dtwise_query


class DtwiseWebAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "dtwise").mkdir()
        (root / "dtwise" / "semantic_planner.py").write_text("", encoding="utf-8")
        (root / "schema.json").write_text("{}", encoding="utf-8")
        (root / "scripts").mkdir()
        (root / "scripts" / "dtwise_bridge.py").write_text("", encoding="utf-8")
        self.root = root
        self.env = {"DTWISE_ROOT": str(root), "DTWISE_SCHEMA": str(root / "schema.json"),
                    "GRAPHDB_SPARQL_ENDPOINT": "http://localhost:7200/repositories/AAS"}

    def test_invokes_exact_frozen_bridge_with_execute(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "question": "List OPCUAconnectivity SignalNames.",
                "mode": "frozen_dtwise_graphdb", "sparql": "SELECT * WHERE {}",
                "executed": True, "answer": {"count": 0, "entities": [],
                "truncated_possible": False}}), "")
        with patch.object(dtwise_query, "ROOT", self.root):
            result = dtwise_query.run_question(" List OPCUAconnectivity SignalNames. ",
                                               runner=runner, environ=self.env)
        self.assertEqual(result["answer"]["count"], 0)
        self.assertEqual(len(calls), 1)
        args, options = calls[0]
        self.assertIn("--execute", args)
        self.assertEqual(args[args.index("--question") + 1], "List OPCUAconnectivity SignalNames.")
        self.assertEqual(args[args.index("--dtwise-root") + 1], str(self.root))
        self.assertEqual(options["timeout"], 120)
        self.assertFalse(options["check"])

    def test_rejects_invalid_question_without_execution(self):
        with self.assertRaises(ValueError):
            dtwise_query.run_question("no", runner=lambda *a, **k: self.fail("runner called"),
                                      environ=self.env)

    def test_missing_configuration_fails_closed(self):
        with self.assertRaises(dtwise_query.DtwiseUnavailable):
            dtwise_query.run_question("List OPCUAconnectivity SignalNames.", environ={})

    def test_frozen_planner_failure_is_not_replanned(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 1, "", "ValueError: rejected")
        with patch.object(dtwise_query, "ROOT", self.root):
            with self.assertRaises(dtwise_query.DtwiseRejected):
                dtwise_query.run_question("List AssetIdentifiers shared by DEXPI and OPCUAConnectivity.",
                                          runner=runner, environ=self.env)

    def test_invalid_or_unexecuted_result_is_not_reported_as_success(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "mode": "frozen_dtwise_graphdb", "executed": False,
                "sparql": "SELECT * WHERE {}", "answer": {}}), "")
        with patch.object(dtwise_query, "ROOT", self.root):
            with self.assertRaises(dtwise_query.DtwiseUnavailable):
                dtwise_query.run_question("List OPCUAconnectivity SignalNames.",
                                          runner=runner, environ=self.env)

    def test_timeout_is_explicit(self):
        def runner(args, **kwargs):
            raise subprocess.TimeoutExpired(args, 120)
        with patch.object(dtwise_query, "ROOT", self.root):
            with self.assertRaises(dtwise_query.DtwiseUnavailable):
                dtwise_query.run_question("List OPCUAconnectivity SignalNames.",
                                          runner=runner, environ=self.env)


if __name__ == "__main__":
    unittest.main()
