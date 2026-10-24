"""Offline tests for bounded temporal operations."""
import unittest
from datetime import datetime, timezone
from process_sim.ai.temporal_plan import validate_temporal_plan, execute_temporal_plan
from process_sim.ai.temporal_registry import temporal_registry

RUN = "c2e5a121-99f8-4d19-b0b5-15cefe5bd611"

class TemporalTests(unittest.TestCase):
    def test_vocabulary(self):
        predicates = {p["predicate"] for p in temporal_registry()["properties"]}
        self.assertIn("https://w3id.org/tep-nexus/ontology/hasFaultEvent", predicates)

    def test_bounded_signal_history(self):
        observed = datetime(2026, 10, 23, tzinfo=timezone.utc)
        result = execute_temporal_plan(
            {"operation": "signal_history", "runId": RUN, "signal": "XMEAS1", "limit": 10},
            samples_reader=lambda run, signal, limit: [(1.5, 8.0, observed)])
        self.assertEqual(result["points"][0]["observedAt"], observed.isoformat())
        self.assertEqual(result["points"][0]["simulationTimeHours"], 1.5)

    def test_invalid_signal(self):
        with self.assertRaises(ValueError):
            validate_temporal_plan({"operation": "signal_history", "runId": RUN,
                                    "signal": "XMEAS99", "limit": 10})

    def test_ambiguous_asset_mapping_is_preserved(self):
        result = execute_temporal_plan(
            {"operation": "asset_history", "runId": RUN,
             "assetIri": "https://example.org/asset/1", "limit": 10},
            asset_reader=lambda asset, run, limit: {"status": "ambiguous", "points": []})
        self.assertEqual(result["result"]["status"], "ambiguous")
