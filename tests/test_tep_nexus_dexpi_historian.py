"""Offline contract tests for the independent DEXPI historian query."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_dexpi_historian import execute, resolve_signal


class HistorianTests(unittest.TestCase):
    def test_unique_mapping(self):
        response = Mock()
        response.json.return_value = {"results": {"bindings": [{
            "assetIdentifier": {"value": "https://aas.example.com/FI105"},
            "signalName": {"value": "XMEAS5"},
        }]}}
        result = resolve_signal("http://graphdb", "FI_105", post=Mock(return_value=response))
        self.assertEqual(result["operational_signal"], "XMEAS5")

    def test_ambiguous_mapping_rejected(self):
        response = Mock()
        response.json.return_value = {"results": {"bindings": [
            {"assetIdentifier": {"value": "a"}, "signalName": {"value": "XMEAS5"}},
            {"assetIdentifier": {"value": "b"}, "signalName": {"value": "XMEAS6"}},
        ]}}
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            resolve_signal("http://graphdb", "FI_105", post=Mock(return_value=response))

    def test_optional_bounds_and_full_series(self):
        mapping = {"engineering_function": "FI_105", "operational_signal": "XMEAS5"}
        calls = []
        def retriever(dsn, run, signal, start, end):
            calls.append((signal, start, end))
            return [{"value": float(i)} for i in range(402)]
        result = execute(
            "Retrieve all recorded values for DEXPI FI_105", "FI_105",
            "077a3c31-44f4-4f3a-b06d-ad52b148fe10", "dsn", "graphdb",
            resolver=lambda url, function: mapping, retriever=retriever,
        )
        self.assertEqual(result["observationCount"], 402)
        self.assertFalse(result["truncated"])
        self.assertEqual(calls, [("XMEAS5", None, None)])

    def test_function_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "must agree"):
            execute("Retrieve FI_106", "FI_105",
                    "077a3c31-44f4-4f3a-b06d-ad52b148fe10", "dsn", "graphdb")


if __name__ == "__main__":
    unittest.main()
