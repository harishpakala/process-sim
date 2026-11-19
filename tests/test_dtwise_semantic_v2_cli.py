"""CLI smoke tests for opt-in semantic-v2 planning and compilation."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from process_sim.dtwise import unified_answer


class SemanticV2CLITests(unittest.TestCase):
    def test_compile_uses_new_planner_without_legacy_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(json.dumps({
                "shape_paths": [{
                    "domain": "ECAD",
                    "node_shape": "https://example.org/DeviceShape",
                    "property_shape": "https://example.org/PropertyShape",
                    "path": "https://example.org/hasAddress",
                    "evidence": True,
                }],
                "relationships": [],
            }), encoding="utf-8")

            def model_reply(url, payload, timeout):
                prompt = json.loads(payload["messages"][1]["content"])
                evidence = prompt["evidence"]
                return {"message": {"content": json.dumps({
                    "version": "2.0",
                    "scope": [evidence["entities"][0]["id"]],
                    "operation": "select_entities",
                    "projections": [],
                    "where": {
                        "operator": "exists",
                        "property_id": evidence["properties"][0]["id"],
                    },
                })}}

            args = [
                "unified_answer", "compile", "--schema", str(schema),
                "--question", "Which ECAD entities have Address?",
                "--semantic-v2", "--planning-mode", "llm_first",
            ]
            stdout = io.StringIO()
            with patch.object(sys, "argv", args), patch.object(
                unified_answer, "_request_json", side_effect=model_reply
            ), patch.object(
                unified_answer, "compile_graph_ir",
                side_effect=AssertionError("legacy compiler was invoked")
            ), contextlib.redirect_stdout(stdout):
                unified_answer.main()
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "compiled")
            self.assertIn("FILTER(EXISTS", result["sparql"])
            self.assertEqual(result["ir"]["version"], "2.0")

    def test_semantic_v2_rejects_hybrid(self):
        with patch.object(sys, "argv", [
            "unified_answer", "compile", "--schema", "unused",
            "--question", "test", "--semantic-v2",
            "--planning-mode", "hybrid",
        ]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                unified_answer.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
