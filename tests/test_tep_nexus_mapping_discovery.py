"""Offline discovery classification tests: no GraphDB connection required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_mapping_discovery import classify_bindings


def row(function_id, signal, ref="urn:ref", asset="urn:asset"):
    return {key: {"value": value} for key, value in {
        "functionId": function_id, "functionRef": ref,
        "signal": signal, "asset": asset}.items()}


class TestMappingDiscovery(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(classify_bindings([])["candidates"], [])

    def test_unique(self):
        x = classify_bindings([row("TI_101", "XMEAS9")])
        self.assertEqual(x["candidates"][0]["status"], "UNIQUE_PROVISIONAL_CANDIDATE")

    def test_duplicate_rows_deduplicated(self):
        x = classify_bindings([row("TI_101", "XMEAS9")] * 2)
        self.assertEqual(x["candidates"][0]["mapping_count"], 1)

    def test_conflicting_signals_are_ambiguous(self):
        x = classify_bindings([row("TI_101", "XMEAS9"), row("TI_101", "XMEAS10")])
        self.assertEqual(x["ambiguous_function_count"], 1)

    def test_conflicting_assets_are_ambiguous(self):
        x = classify_bindings([row("TI_101", "XMEAS9"), row("TI_101", "XMEAS9", asset="urn:other")])
        self.assertEqual(x["candidates"][0]["mapping_count"], 2)

    def test_invalid_row_recorded(self):
        x = classify_bindings([{"functionId": {"value": "TI_101"}}])
        self.assertEqual(len(x["invalid_rows"]), 1)

    def test_sorted_functions(self):
        x = classify_bindings([row("TI_102", "X2"), row("TI_101", "X1")])
        self.assertEqual([c["engineering_function"] for c in x["candidates"]], ["TI_101", "TI_102"])


if __name__ == "__main__":
    unittest.main()
