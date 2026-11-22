"""Regression tests for the on-demand VTKG question handoff."""
import unittest
from unittest.mock import patch
from uuid import uuid4

from process_sim.api.vtkg_query import explore_signal_knowledge


class ExploreSignalTests(unittest.TestCase):
    def test_supported_time_intervals_and_local_id(self):
        cases = [
            (None, None, "for all simulation times"),
            (10, 20, "between simulation seconds 10 and 20"),
            (10, None, "from simulation second 10 onward"),
            (None, 20, "up to simulation second 20"),
        ]
        for start, end, phrase in cases:
            with self.subTest(start=start, end=end):
                run = str(uuid4())
                captured = []

                def fake_builder(payload, *, environ=None):
                    captured.append(payload)
                    return {"mapping": {"operational_signal": "XMEAS9"},
                            "vtkgStatus": "constructed", "vtkg": {"nodes": [], "edges": []}}

                with patch("process_sim.api.vtkg_query.discover_semantic_mappings",
                           side_effect=lambda endpoint, domain:
                           {"TI_101": {("asset-1", "XMEAS9")}} if domain == "DEXPI" else {}), \\
                     patch("process_sim.api.vtkg_query.run_historian_question", side_effect=fake_builder):
                    result = explore_signal_knowledge({
                        "signal_id": "XMEAS9", "run_id": run,
                        "start_simulation_seconds": start, "end_simulation_seconds": end,
                    }, environ={"GRAPHDB_SPARQL_ENDPOINT": "https://example.invalid/sparql"})
                self.assertEqual(result["status"], "constructed")
                self.assertIn("TI_101", captured[0]["question"])
                self.assertIn(phrase, captured[0]["question"])
                self.assertIn(run, captured[0]["question"])

    def test_unmapped_signal_remains_unresolved(self):
        with patch("process_sim.api.vtkg_query.discover_semantic_mappings", return_value={}):
            result = explore_signal_knowledge({
                "signal_id": "S1", "run_id": str(uuid4()),
                "start_simulation_seconds": None, "end_simulation_seconds": None,
            }, environ={"GRAPHDB_SPARQL_ENDPOINT": "https://example.invalid/sparql"})
        self.assertEqual(result["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
