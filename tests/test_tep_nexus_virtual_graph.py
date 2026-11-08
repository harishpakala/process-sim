"""Offline contract tests for the first virtual temporal graph projection."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_virtual_graph import project

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"


def fixture():
    return {
        "validatedPlan": {"engineering_function": "TI_101"},
        "engineeringMapping": {
            "engineering_function": "TI_101",
            "operational_signal": "XMEAS9",
            "asset_uri": "https://example.org/assetinventory/asset-1",
        },
        "temporalEvidence": {
            "runId": RUN, "signal": "XMEAS9",
            "faultCommands": [{
                "event_id": "evt-1", "action": "inject",
                "simulation_time_hours": 0.01,
                "observed_at": "2026-11-08T15:00:00+00:00",
            }],
            "windows": [{
                "truncated": False,
                "samples": [{
                    "simulationTimeHours": 0.009,
                    "value": 125.0,
                    "observedAt": "2026-11-08T15:00:01+00:00",
                    "temporalRelations": [{"faultId": "fault-1", "relation": "BEFORE"}],
                }],
            }],
        },
    }


class VirtualGraphTests(unittest.TestCase):
    def test_graph_projection_is_deterministic_and_not_materialized(self):
        graph = project(fixture())
        self.assertEqual(graph, project(fixture()))
        self.assertFalse(graph["materializedInGraphDB"])
        self.assertEqual(len(graph["nodes"]), 6)
        self.assertEqual(len(graph["edges"]), 6)
        observation = next(n for n in graph["nodes"] if n["type"] == "VirtualObservation")
        self.assertEqual(observation["value"], 125.0)
        self.assertEqual(observation["temporalRelations"][0]["relation"], "BEFORE")
        self.assertEqual(observation["identityScope"],
                         "QUERY_WINDOW_ORDINAL_NOT_DATABASE_PRIMARY_KEY")

    def test_mapping_mismatch_rejected(self):
        query = fixture()
        query["engineeringMapping"]["operational_signal"] = "XMEAS8"
        with self.assertRaisesRegex(ValueError, "historian signal"):
            project(query)

    def test_invalid_run_rejected(self):
        query = fixture()
        query["temporalEvidence"]["runId"] = "not-a-uuid"
        with self.assertRaises(ValueError):
            project(query)

    def test_unrecognized_relation_rejected(self):
        query = fixture()
        query["temporalEvidence"]["windows"][0]["samples"][0]["temporalRelations"][0]["relation"] = "CAUSED_BY"
        with self.assertRaisesRegex(ValueError, "Unsupported temporal relation"):
            project(query)

    def test_uri_escapes_signal_identifiers(self):
        query = fixture()
        query["engineeringMapping"]["operational_signal"] = "XMEAS/9"
        query["temporalEvidence"]["signal"] = "XMEAS/9"
        graph = project(query)
        signal = next(n for n in graph["nodes"] if n["type"] == "OperationalSignal")
        self.assertIn("XMEAS%2F9", signal["id"])


if __name__ == "__main__":
    unittest.main()
