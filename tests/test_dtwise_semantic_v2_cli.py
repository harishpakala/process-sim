"""Offline tests for opt-in semantic v2 experimental CLI dispatch."""
import unittest
from unittest.mock import patch

from process_sim.dtwise.experimental_multihop_cli import plan_experimental_multihop


class SemanticV2CLITests(unittest.TestCase):
    def test_v2_dispatch_without_question_regex_heuristics(self):
        catalog = {"entities": [{
            "domain": "opc", "shape": "urn:SignalMapping",
            "display_name": "SignalMapping",
            "properties": ["urn:hasSignalName"]}]}
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=catalog), patch(
                "process_sim.dtwise.semantic_v2_adapter.select_and_bind_v2",
                return_value=({"ir_version": "1.0"}, {"path_id": "PATH_0"})
                ) as selector:
            plan, selection = plan_experimental_multihop(
                "An unconstrained natural language question", {}, [],
                model="mock", ollama_host="http://localhost:11434",
                timeout=1, planning_mode="semantic_v2")
        self.assertEqual(selection["path_id"], "PATH_0")
        self.assertEqual(plan["ir_version"], "1.0")
        paths = selector.call_args.args[1]
        self.assertEqual(paths, [{"nodes": [("opc", "urn:SignalMapping")],
                                  "steps": []}])

    def test_v2_rejects_excessive_evidence_candidates(self):
        catalog = {"entities": [
            {"domain": "opc", "shape": "urn:Shape" + str(i),
             "display_name": "Shape" + str(i), "properties": []}
            for i in range(33)]}
        with patch("process_sim.dtwise.experimental_multihop_cli.catalog_from_schema",
                   return_value=catalog):
            with self.assertRaisesRegex(ValueError, "candidate limit"):
                plan_experimental_multihop(
                    "Count all entities", {}, [], model="mock",
                    ollama_host="http://localhost:11434", timeout=1,
                    planning_mode="semantic_v2")


if __name__ == "__main__":
    unittest.main()
