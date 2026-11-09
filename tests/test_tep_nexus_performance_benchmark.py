"""Offline tests for repeated VTKG benchmark statistics and safety."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_performance_benchmark import benchmark, percentile, write_outputs

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"


def fake_evaluator(*args, **kwargs):
    return {
        "summary": {"status": "PASS"},
        "cases": [{"function": "TI_101", "windowSeconds": [20, 60],
                   "latencyMs": 12.5, "observationCount": 14,
                   "truncated": False, "status": "PASS"}],
    }


class BenchmarkTests(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(percentile([1, 2, 3, 4], 95), 4)
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2)
        self.assertIsNone(percentile([], 99))

    def test_warmups_excluded_and_percentiles(self):
        calls = []
        def evaluator(*args, **kwargs):
            calls.append(True)
            return fake_evaluator()
        report = benchmark(RUN, [[20, 60]], dsn="unused", graphdb_url="unused",
                           warmups=2, repetitions=3, evaluator=evaluator)
        self.assertEqual(len(calls), 5)
        self.assertEqual(report["summary"]["measuredCases"], 3)
        self.assertEqual(report["summary"]["p95LatencyMs"], 12.5)
        self.assertEqual(report["summary"]["status"], "PASS")

    def test_failure_aborts_benchmark(self):
        def failing(*args, **kwargs):
            return {"summary": {"status": "FAIL"}}
        with self.assertRaises(RuntimeError):
            benchmark(RUN, [[20, 60]], dsn="unused", graphdb_url="unused",
                      warmups=0, evaluator=failing)

    def test_invalid_inputs(self):
        for overrides in ({"repetitions": 0}, {"warmups": -1},
                          {"repetitions": True}, {"windows": [[float("nan"), 60]]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                kw = {"dsn": "unused", "graphdb_url": "unused",
                      "warmups": 0, "evaluator": fake_evaluator}
                windows = overrides.pop("windows", [[20, 60]])
                kw.update(overrides)
                benchmark(RUN, windows, **kw)

    def test_json_csv_export(self):
        report = benchmark(RUN, [[20, 60]], dsn="unused", graphdb_url="unused",
                           warmups=0, repetitions=1, evaluator=fake_evaluator)
        with tempfile.TemporaryDirectory() as tmp:
            j, c = Path(tmp) / "benchmark.json", Path(tmp) / "benchmark.csv"
            write_outputs(report, j, c)
            self.assertTrue(j.is_file())
            with c.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["function"], "TI_101")


if __name__ == "__main__":
    unittest.main()
