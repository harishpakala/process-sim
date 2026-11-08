"""Tests for GraphDB snapshot normalization and lifecycle CLI adapters."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from selira_integration.graphdb_snapshot import (
    _iri, snapshot_from_rows, save_snapshot, load_snapshot, read_snapshot)
from selira_integration.lifecycle import Lifecycle, Snapshot

class GraphDBSnapshotTests(unittest.TestCase):
    def test_named_graph_iri_validation(self):
        self.assertEqual(_iri("https://example.org/graph/a"),
                         "<https://example.org/graph/a>")
        for bad in ("not-an-iri", "https://example.org/>", "file:///tmp/a"):
            with self.assertRaises(ValueError):
                _iri(bad)

    def test_literal_identifiers_and_duplicate_product_ids(self):
        ref = "https://example.org/product-types/A"
        snapshot = snapshot_from_rows("R1",
            [{"asset": "urn:asset:1", "ref": ref}],
            [{"product": "urn:product:1", "identifier": ref},
             {"product": "urn:product:2", "identifier": ref}], complete=True)
        self.assertEqual(snapshot.catalog["urn:product:2"], ref)
        self.assertEqual(LifecycleCheck(snapshot), "INVALID")

    def test_ambiguous_per_entity_values_rejected(self):
        with self.assertRaises(ValueError):
            snapshot_from_rows("R1", [
                {"asset": "a", "ref": "x"}, {"asset": "a", "ref": "y"}],
                [], complete=True)
        with self.assertRaises(ValueError):
            snapshot_from_rows("R1", [], [
                {"product": "p", "identifier": "x"},
                {"product": "p", "identifier": "y"}], complete=True)

    @patch("selira_integration.graphdb_snapshot.select")
    def test_reads_explicit_named_graphs(self, select):
        select.side_effect = [
            [{"asset": "a", "ref": "x"}],
            [{"product": "p", "identifier": "x"}]]
        snap = read_snapshot("http://localhost:7200/repositories/test",
            "https://example.org/graph/inventory",
            "https://example.org/graph/catalog", "R1", complete=True)
        self.assertEqual(snap.assigned, {"a": "x"})
        self.assertEqual(len(select.call_args_list), 2)
        self.assertIn("GRAPH <https://example.org/graph/inventory>",
                      select.call_args_list[0].args[1])
        self.assertIn("GRAPH <https://example.org/graph/catalog>",
                      select.call_args_list[1].args[1])

    def test_snapshot_round_trip_and_selective_baseline(self):
        before = Snapshot("R1", {"a": "x", "b": "y"}, {"p": "x", "q": "y"})
        after = Snapshot("R2", {"a": "x", "b": "y"}, {"p": "z", "q": "y"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            save_snapshot(before, path)
            self.assertEqual(load_snapshot(path), before)
            lifecycle = Lifecycle(Path(directory) / "history.jsonl")
            lifecycle.initialize(before)
            result = lifecycle.apply(before, after)
            self.assertEqual(result["affected"], ["a"])
            self.assertTrue(result["baseline_agreement"])
            self.assertTrue(result["unaffected_unchanged"])

def LifecycleCheck(snapshot):
    from selira_integration.lifecycle import check
    return check(snapshot, "urn:asset:1")

if __name__ == "__main__":
    unittest.main()
