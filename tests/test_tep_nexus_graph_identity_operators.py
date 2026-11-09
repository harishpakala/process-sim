"""Identity and operator regression tests for TEP NEXUS virtual graph."""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_live_virtual_graph import observation_fingerprint
from tep_nexus_virtual_graph import project
from tep_nexus_graph_operators import resolve_function, get_observations, traverse_relationships

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"


def fixture(sample):
    return {
        "validatedPlan": {"engineering_function": "TI_101"},
        "engineeringMapping": {"engineering_function": "TI_101",
                               "operational_signal": "XMEAS9",
                               "asset_uri": "https://example.org/assetinventory/test"},
        "temporalEvidence": {"runId": RUN, "signal": "XMEAS9",
                             "faultCommands": [], "windows": [
                                 {"truncated": False, "samples": [sample]}]},
    }


class IdentityOperatorTests(unittest.TestCase):
    def test_fingerprint_consistent_across_timezone_representation(self):
        t = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)
        same = t.astimezone(timezone(timedelta(hours=1)))
        self.assertEqual(observation_fingerprint(RUN, "XMEAS9", 0.01, 12.0, t),
                         observation_fingerprint(RUN, "XMEAS9", 0.01, 12.0, same))

    def test_fingerprint_distinguishes_value_and_signal(self):
        t = datetime(2026, 11, 8, tzinfo=timezone.utc)
        base = observation_fingerprint(RUN, "XMEAS9", 0.01, 12.0, t)
        self.assertNotEqual(base, observation_fingerprint(RUN, "XMEAS9", 0.01, 13.0, t))
        self.assertNotEqual(base, observation_fingerprint(RUN, "XMEAS8", 0.01, 12.0, t))

    def test_virtual_identity_consistent_across_window_positions(self):
        stamp = datetime(2026, 11, 8, tzinfo=timezone.utc)
        fingerprint = observation_fingerprint(RUN, "XMEAS9", 0.01, 12.0, stamp)
        sample = {"observationFingerprint": fingerprint,
                  "simulationTimeHours": 0.01, "value": 12.0,
                  "observedAt": stamp.isoformat(), "temporalRelations": []}
        a = project(fixture(sample))
        b_input = fixture(sample)
        b_input["temporalEvidence"]["windows"].insert(
            0, {"truncated": False, "samples": []})
        b = project(b_input)
        ida = next(n["id"] for n in a["nodes"] if n["type"] == "VirtualObservation")
        idb = next(n["id"] for n in b["nodes"] if n["type"] == "VirtualObservation")
        self.assertEqual(ida, idb)

    def test_graph_operators(self):
        sample = {"simulationTimeHours": 0.01, "value": 12.0,
                  "observedAt": "2026-11-08T00:00:00+00:00",
                  "temporalRelations": []}
        graph = project(fixture(sample))
        found = resolve_function(graph, "TI_101")
        self.assertEqual(len(found["relationships"]), 2)
        self.assertEqual(len(get_observations(graph, start_seconds=35, end_seconds=37)), 1)
        self.assertEqual(get_observations(graph, start_seconds=40), [])
        self.assertEqual(len(traverse_relationships(
            graph, found["function"]["id"], predicate="mapsToSignal")), 1)
        with self.assertRaises(ValueError):
            traverse_relationships(graph, "unknown")
        with self.assertRaises(ValueError):
            get_observations(graph, start_seconds=50, end_seconds=20)


if __name__ == "__main__":
    unittest.main()
