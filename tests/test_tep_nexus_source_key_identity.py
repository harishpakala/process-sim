"""Offline regression tests for source-backed historian observation identity."""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_live_virtual_graph import observation_primary_key, observation_fingerprint, retrieve_observations
from tep_nexus_virtual_graph import project

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
STAMP = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)


class SourceIdentityTests(unittest.TestCase):
    def test_value_changes_do_not_change_source_key(self):
        a = observation_primary_key(RUN, "XMEAS9", STAMP)
        b = observation_primary_key(RUN, "XMEAS9", STAMP)
        self.assertEqual(a, b)
        self.assertNotEqual(observation_fingerprint(RUN, "XMEAS9", .01, 1, STAMP),
                            observation_fingerprint(RUN, "XMEAS9", .01, 2, STAMP))

    def test_timestamp_and_signal_change_identity(self):
        original = observation_primary_key(RUN, "XMEAS9", STAMP)
        self.assertNotEqual(original, observation_primary_key(RUN, "XMEAS9", STAMP + timedelta(microseconds=1)))
        self.assertNotEqual(original, observation_primary_key(RUN, "XMEAS8", STAMP))

    def test_timezone_normalization(self):
        same = STAMP.astimezone(timezone(timedelta(hours=2)))
        self.assertEqual(observation_primary_key(RUN, "XMEAS9", STAMP),
                         observation_primary_key(RUN, "XMEAS9", same))

    def test_project_uses_key_and_retains_content_fingerprint(self):
        sample = {"observationPrimaryKeyHash": "abc123", "observationFingerprint": "content",
                  "simulationTimeHours": .01, "observedAt": STAMP.isoformat(),
                  "value": 4.0, "temporalRelations": []}
        query = {"validatedPlan": {"engineering_function": "TI_101"},
                 "engineeringMapping": {"engineering_function": "TI_101",
                                        "operational_signal": "XMEAS9",
                                        "asset_uri": "https://example.org/asset/test"},
                 "temporalEvidence": {"runId": RUN, "signal": "XMEAS9", "faultCommands": [],
                                      "windows": [{"samples": [sample], "truncated": False}]}}
        graph = project(query)
        observation = next(n for n in graph["nodes"] if n["type"] == "VirtualObservation")
        self.assertTrue(observation["id"].endswith("/abc123"))
        self.assertEqual(observation["contentFingerprint"], "content")
        self.assertEqual(observation["identityScope"], "SOURCE_COMPOSITE_PRIMARY_KEY_SHA256")

    def test_duplicate_primary_key_rejected(self):
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.fetchall.return_value = [(.01, 1.0, STAMP), (.02, 2.0, STAMP)]
        conn = MagicMock()
        conn.__enter__.return_value = conn
        tx = MagicMock()
        tx.__enter__.return_value = tx
        conn.transaction.return_value = tx
        conn.cursor.return_value = cur
        req = {"run_id": RUN, "start_simulation_seconds": 0,
               "end_simulation_seconds": 100, "limit": 5}
        with self.assertRaisesRegex(ValueError, "duplicate historian"):
            retrieve_observations("unused", req, "XMEAS9", connection_factory=lambda dsn: conn)


if __name__ == "__main__":
    unittest.main()
