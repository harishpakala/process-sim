"""Offline tests for the Semantic v2 benchmark runner."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_dtwise_semantic_v2_benchmark.py"
spec = importlib.util.spec_from_file_location("dtwise_benchmark_runner", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class SemanticV2BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(
            schema="schema.json", mappings="mappings.json",
            endpoint=None, model="mock", ollama_host="http://localhost:11434",
            llm_timeout=20, case_timeout=60, keep_alive=None,
            graph_mode="all_named")
        self.case = {"id": "B01", "category": "basic",
                     "question": "Get SignalName."}

    def test_compile_success_does_not_claim_answer_correctness(self):
        def runner(command, **kwargs):
            self.assertIn("semantic_v2", command)
            self.assertIn("--experimental-multihop", command)
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "status": "compiled", "ir": {}, "sparql": "SELECT * WHERE {}",
                "timings": {"planning_seconds": 0.1,
                            "compilation_seconds": 0.1}}))
        result = benchmark.evaluate_case(self.case, self.args, runner)
        self.assertEqual(result["compilation"], "passed")
        self.assertEqual(result["execution"], "not_run")
        self.assertEqual(result["answer_correctness"], "unverified")

    def test_graphdb_execution_is_separate_from_correctness(self):
        self.args.endpoint = "http://localhost:7200/repositories/AAS"
        def runner(command, **kwargs):
            self.assertIn("--endpoint", command)
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "status": "executed", "results": {"results": {"bindings": []}},
                "timings": {"planning_seconds": 1, "compilation_seconds": 1}}))
        result = benchmark.evaluate_case(self.case, self.args, runner)
        self.assertEqual(result["execution"], "passed")
        self.assertEqual(result["answer_correctness"], "unverified")

    def test_failure_is_reported_not_counted_as_pass(self):
        def runner(*args, **kwargs):
            return SimpleNamespace(returncode=1, stderr="",
                                   stdout=json.dumps({
                                       "status": "rejected_or_failed",
                                       "error": "No evidenced path",
                                       "timings": {}}))
        result = benchmark.evaluate_case(self.case, self.args, runner)
        self.assertEqual(result["compilation"], "failed_or_unknown")
        self.assertEqual(result["error"], "No evidenced path")

    def test_manifest_requires_all_53_unique_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps([self.case] * 53), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "53 uniquely"):
                benchmark.load_cases(path)


if __name__ == "__main__":
    unittest.main()
