"""Offline regression tests for the fault-relative virtual Temporal KG query."""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from tep_nexus_fault_relative_query import retrieve_fault_relative_evidence

RUN = "a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5"
T0 = datetime.now(timezone.utc) - timedelta(seconds=3)


class Cursor:
    def __init__(self, events, samples):
        self.events, self.samples = events, samples
        self.rows = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "count(*)" in sql:
            self.rows = [(len(self.events),)]
        elif "FROM public.fault_events" in sql:
            self.rows = self.events
        elif "LIMIT 1" in sql and "signal_samples" in sql:
            self.rows = [max(self.samples, key=lambda r: r[2])] if self.samples else []
        else:
            _, _, low, high, limit = params
            self.rows = [r for r in self.samples if low <= r[0] <= high][:limit]
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return self

    def execute(self, sql):
        assert sql == "SET TRANSACTION READ ONLY"

    def cursor(self):
        return self._cursor


class FaultRelativeQueryTests(unittest.TestCase):
    def test_open_interval_is_unconfirmed(self):
        events = [
            (UUID("3ccebd11-1949-4425-86c8-9d5e328147e8"),
             UUID(RUN), T0, 0.01, "inject", "paper-fault-02", "XMEAS9"),
        ]
        samples = [(0.005, 10.0, T0), (0.015, 15.0, T0)]
        cursor = Cursor(events, samples)
        result = retrieve_fault_relative_evidence(
            "unused", RUN, "XMEAS9", window_minutes=2,
            connection_factory=lambda _: Connection(cursor),
        )
        self.assertEqual(result["faultCommandIntervals"][0]["status"], "OPEN_UNCONFIRMED")
        labels = [s["temporalRelations"][0]["relation"]
                  for s in result["windows"][0]["samples"]]
        self.assertEqual(labels, ["BEFORE", "DURING_UNCONFIRMED"])
        self.assertIsNotNone(result["latestPersisted"])
        self.assertTrue(any("READ ONLY" in q for q, _ in cursor.queries) is False)

    def test_event_limit_fails_closed(self):
        events = [(None, None, None, None, None, None, None)] * 2
        with self.assertRaisesRegex(ValueError, "exceeds event_limit"):
            retrieve_fault_relative_evidence(
                "unused", RUN, "XMEAS9", event_limit=1,
                connection_factory=lambda _: Connection(Cursor(events, [])),
            )

    def test_invalid_run_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_fault_relative_evidence("unused", "not-a-uuid", "XMEAS9")


if __name__ == "__main__":
    unittest.main()
