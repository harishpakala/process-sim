"""Offline contract tests for live GraphDB/TimescaleDB virtual graph orchestration."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_live_virtual_graph import execute, retrieve_observations, validate_request

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"


def request():
    return {"engineering_function": "TI_101", "run_id": RUN,
            "start_simulation_seconds": 20, "end_simulation_seconds": 60,
            "limit": 2}


def mapping():
    return {"engineering_function": "TI_101", "operational_signal": "XMEAS9",
            "asset_uri": "https://example.org/assetinventory/test"}


class LiveVirtualGraphTests(unittest.TestCase):
    def test_request_bounds_and_limit_fail_closed(self):
        for start, end, limit in [(30, 20, 2), (-1, 20, 2), (0, 20, 0),
                                  (0, 20, True), (float("nan"), 20, 2)]:
            with self.subTest(start=start, end=end, limit=limit):
                with self.assertRaises(ValueError):
                    validate_request("TI_101", RUN, start, end, limit)

    def test_graph_is_fault_independent_and_preserves_provenance(self):
        graph = execute(request(), dsn="unused", graphdb_url="unused",
                        registry_loader=lambda *args: {"TI_101": {"operational_signal": "XMEAS9"}},
                        mapping_resolver=lambda *args: mapping(),
                        observation_retriever=lambda *args: {
                            "truncated": False, "samples": [{
                                "simulationTimeHours": 0.01, "value": 123.0,
                                "observedAt": "2026-11-08T15:00:00+00:00",
                                "temporalRelations": [],
                            }],
                        })
        self.assertEqual(graph["result"]["observationCount"], 1)
        self.assertFalse(graph["materializedInGraphDB"])
        self.assertEqual(graph["provenance"]["sharedRunProvenance"], "NOT_VERIFIED")
        self.assertEqual(sum(n["type"] == "RecordedFaultCommand" for n in graph["nodes"]), 0)
        self.assertEqual(sum(n["type"] == "VirtualObservation" for n in graph["nodes"]), 1)

    def test_mapping_mismatch_rejected(self):
        wrong = {**mapping(), "operational_signal": "XMEAS8"}
        with self.assertRaisesRegex(ValueError, "Live mapping"):
            execute(request(), dsn="unused", graphdb_url="unused",
                    registry_loader=lambda *args: {"TI_101": {"operational_signal": "XMEAS9"}},
                    mapping_resolver=lambda *args: wrong,
                    observation_retriever=lambda *args: self.fail("SQL must not be queried"))

    def test_sql_is_parameterized_read_only_and_truncation_probed(self):
        cur = Mock()
        cur.__enter__ = Mock(return_value=cur)
        cur.__exit__ = Mock(return_value=False)
        stamp = datetime(2026, 11, 8, tzinfo=timezone.utc)
        cur.fetchall.return_value = [(0.01, 1.0, stamp), (0.012, 2.0, stamp),
                                     (0.013, 3.0, stamp)]
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        tx = Mock()
        tx.__enter__ = Mock(return_value=tx)
        tx.__exit__ = Mock(return_value=False)
        conn.transaction.return_value = tx
        conn.cursor.return_value = cur
        result = retrieve_observations("dsn", request(), "XMEAS9",
                                       connection_factory=lambda dsn: conn)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["samples"]), 2)
        conn.execute.assert_called_once_with("SET TRANSACTION READ ONLY")
        sql, params = cur.execute.call_args.args
        self.assertIn("run_id = %s::uuid", sql)
        self.assertIn("signal_id = %s", sql)
        self.assertEqual(params, (RUN, "XMEAS9", 20 / 3600, 60 / 3600, 3))


if __name__ == "__main__":
    unittest.main()
