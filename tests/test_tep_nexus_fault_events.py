"""Unit tests for read-only fault event retrieval with mocked psycopg."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_fault_events import fetch_recorded_commands


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params):
        self.query, self.params = query, params

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, cursor):
        self.c = cursor
        self.readonly = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def transaction(self):
        return self

    def execute(self, query):
        if query != "SET TRANSACTION READ ONLY":
            raise AssertionError(query)
        self.readonly = True

    def cursor(self):
        return self.c


class FaultEventRetrievalTests(unittest.TestCase):
    def test_run_scoped_time_bounds_and_source_fields(self):
        event = str(UUID("f65f88e0-59d3-4ca6-a45e-b969af5641a2"))
        run = str(UUID("077a3c31-44f4-4f3a-b06d-ad52b148fe10"))
        stamp = datetime(2026, 11, 22, tzinfo=timezone.utc)
        cursor = Cursor([(UUID(event), "activate", 1.5, stamp,
                          "fault-1", "step", "XMEAS1", 2.0, "operator")])
        connection = Connection(cursor)
        with patch.dict(sys.modules, {"psycopg": types.SimpleNamespace(connect=lambda dsn: connection)}):
            result = fetch_recorded_commands("fake-dsn", run, 3600, 7200)
        self.assertTrue(connection.readonly)
        self.assertIn("FROM public.fault_events", cursor.query)
        self.assertIn("run_id = %s::uuid", cursor.query)
        self.assertEqual(cursor.params, [run, 1.0, 2.0])
        self.assertEqual(result[0]["event_id"], event)
        self.assertEqual(result[0]["observed_at"], stamp.isoformat())
        self.assertEqual(result[0]["target"], "XMEAS1")


if __name__ == "__main__":
    unittest.main()
