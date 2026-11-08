"""Offline tests for the historian identity schema audit."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_identity_schema_audit import assess, inspect

COLUMNS = [
    {"name": "id", "dataType": "bigint", "notNull": True},
    {"name": "run_id", "dataType": "uuid", "notNull": True},
    {"name": "signal_id", "dataType": "text", "notNull": True},
]


class IdentityAuditTests(unittest.TestCase):
    def test_primary_key_is_candidate(self):
        result = assess(COLUMNS, [{"name": "signal_samples_pkey", "type": "PRIMARY KEY",
                                   "columns": ["id"]}], [])
        self.assertTrue(result["stableDeclaredRowKey"])
        self.assertTrue(result["primaryKeyPresent"])
        self.assertEqual(result["candidateKeys"][0]["columns"], ["id"])

    def test_nullable_unique_not_sufficient(self):
        cols = COLUMNS + [{"name": "optional_tag", "dataType": "text", "notNull": False}]
        result = assess(cols, [{"name": "optional_unique", "type": "UNIQUE",
                                "columns": ["optional_tag"]}], [])
        self.assertFalse(result["stableDeclaredRowKey"])

    def test_nonnull_unique_is_candidate(self):
        result = assess(COLUMNS, [{"name": "run_signal_unique", "type": "UNIQUE",
                                   "columns": ["run_id", "signal_id"]}], [])
        self.assertTrue(result["stableDeclaredRowKey"])
        self.assertFalse(result["primaryKeyPresent"])

    def test_index_only_does_not_prove_key(self):
        result = assess(COLUMNS, [], [{"unique": True, "partial": False}])
        self.assertFalse(result["stableDeclaredRowKey"])

    def test_missing_table_fails_closed(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (None,)
        conn = MagicMock()
        conn.__enter__.return_value = conn
        tx = MagicMock()
        tx.__enter__.return_value = tx
        conn.transaction.return_value = tx
        conn.cursor.return_value = cursor
        with self.assertRaisesRegex(ValueError, "not found"):
            inspect("unused", connect=lambda dsn: conn)
        conn.execute.assert_called_once_with("SET TRANSACTION READ ONLY")

    def test_catalog_queries_are_read_only(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ("signal_samples",)
        cursor.fetchall.side_effect = [
            [("id", "bigint", True), ("run_id", "uuid", True)],
            [("signal_samples_pkey", "p", ["id"], "PRIMARY KEY (id)")],
            [("signal_samples_pkey", True, True, True, True, False, False,
              "CREATE UNIQUE INDEX signal_samples_pkey ...")],
        ]
        conn = MagicMock()
        conn.__enter__.return_value = conn
        tx = MagicMock()
        tx.__enter__.return_value = tx
        conn.transaction.return_value = tx
        conn.cursor.return_value = cursor
        result = inspect("unused", connect=lambda dsn: conn)
        self.assertTrue(result["assessment"]["primaryKeyPresent"])
        self.assertTrue(result["readOnly"])
        self.assertEqual(cursor.execute.call_count, 4)
        for call in cursor.execute.call_args_list:
            self.assertEqual(call.args[1], ("public.signal_samples",))


if __name__ == "__main__":
    unittest.main()
