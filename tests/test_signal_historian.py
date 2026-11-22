"""Focused contract tests for the signal-first historian API (no database required)."""
import unittest
from unittest.mock import patch
from uuid import uuid4

from process_sim.api import signal_historian


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def transaction(self):
        return self

    def execute(self, *_):
        return None

    def cursor(self):
        return self.cursor_obj


class SignalHistorianTests(unittest.TestCase):
    def setUp(self):
        self.run_id = str(uuid4())
        self.env = {"TEP_TIMESCALE_DSN": "fake"}

    def test_signal_discovery_includes_source_and_unclassified(self):
        conn = FakeConnection([("XMEAS9", 12, "Unclassified", None, "unclassified", "NOT_VERIFIED")])
        result = signal_historian.discover_signals(
            self.run_id, measurement_type="Unclassified", environ=self.env,
            connection_factory=lambda _: conn)
        self.assertEqual(result["signals"][0]["signal_id"], "XMEAS9")
        self.assertEqual(result["signals"][0]["verification_status"], "NOT_VERIFIED")
        self.assertIn("LEFT JOIN public.signal_metadata", conn.cursor_obj.executed[0][0])

    def test_rejects_unsupported_type_before_database_access(self):
        with self.assertRaises(ValueError):
            signal_historian.discover_signals(self.run_id, measurement_type="Unknown", environ=self.env)

    def test_measurement_types_includes_zero_count_buckets(self):
        conn = FakeConnection([("Temperature", 2)])
        result = signal_historian.discover_measurement_types(
            environ=self.env, connection_factory=lambda _: conn)
        self.assertEqual(len(result["measurement_types"]), 5)
        self.assertEqual(result["measurement_types"][-1], {"name": "Unclassified", "signal_count": 0})

    def test_signal_values_do_not_require_graphdb(self):
        from datetime import datetime, timezone
        conn = FakeConnection([(0.01, 123.0, datetime(2026, 1, 1, tzinfo=timezone.utc))])
        payload = {"run_id": self.run_id, "signal_id": "XMEAS9",
                   "start_simulation_seconds": 10, "end_simulation_seconds": 60}
        result = signal_historian.retrieve_signal(
            payload, environ=self.env, connection_factory=lambda _: conn)
        self.assertEqual(result["observationCount"], 1)
        self.assertEqual(result["vtkgStatus"], "not_requested")
        self.assertEqual(conn.cursor_obj.executed[0][1][-1], 5001)

    def test_rejects_invalid_time_window(self):
        with self.assertRaises(ValueError):
            signal_historian.retrieve_signal({"run_id": self.run_id, "signal_id": "XMEAS9",
                "start_simulation_seconds": 30, "end_simulation_seconds": 20}, environ=self.env)


if __name__ == "__main__":
    unittest.main()
