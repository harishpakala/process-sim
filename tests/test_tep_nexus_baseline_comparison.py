"""Offline tests for paired virtual/direct historian benchmark."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_baseline_comparison import compare, write_outputs

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
REGISTRY = {"TI_101": {"operational_signal": "XMEAS9"}}
FP = "a" * 64


def registry_loader(*args):
    return REGISTRY


def virtual_executor(request, **kwargs):
    return {
        "nodes": [
            {"type": "OperationalSignal", "signalId": "XMEAS9"},
            {"type": "VirtualObservation", "id": "https://example.org/observation/" + FP},
        ],
        "result": {"observationCount": 1, "truncated": False},
    }


def direct_retriever(dsn, request, signal):
    return {"samples": [{"observationFingerprint": FP}], "truncated": False}


class ComparisonTests(unittest.TestCase):
    def kwargs(self):
        return dict(dsn="unused", graphdb_url="unused",
                    registry_loader=registry_loader, virtual_executor=virtual_executor,
                    direct_retriever=direct_retriever, warmups=1, repetitions=2)

    def test_paired_matches(self):
        report = compare(RUN, [[20, 60]], **self.kwargs())
        self.assertEqual(report["summary"]["pairedCases"], 2)
        self.assertEqual(report["summary"]["matchingPairs"], 2)
        self.assertTrue(all(r["fingerprintsEqual"] for r in report["measurements"]))

    def test_mismatch_rejected(self):
        def changed(*args, **kwargs):
            return {"samples": [{"observationFingerprint": "b" * 64}],
                    "truncated": False}
        kw = self.kwargs()
        kw["direct_retriever"] = changed
        with self.assertRaises(RuntimeError):
            compare(RUN, [[20, 60]], **kw)

    def test_invalid_window_and_function(self):
        for windows, functions in (([[60, 20]], None), ([[20, 60]], ["BAD"])):
            with self.subTest(windows=windows, functions=functions), self.assertRaises(ValueError):
                compare(RUN, windows, functions=functions, **self.kwargs())

    def test_export(self):
        report = compare(RUN, [[20, 60]], **self.kwargs())
        with tempfile.TemporaryDirectory() as tmp:
            j, c = Path(tmp) / "report.json", Path(tmp) / "report.csv"
            write_outputs(report, j, c)
            self.assertTrue(j.exists())
            self.assertEqual(len(c.read_text().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
