"""Offline tests for descriptive fault-relative analytics and HTML timeline."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tep_nexus_fault_relative_analysis import analyze, render_html, assess_baseline


class FaultAnalysisTests(unittest.TestCase):
    def evidence(self, truncated=False):
        return {
            "runId": "a436c579-4f6a-4a60-b1b8-5a0de6ffdbf5",
            "signal": "XMEAS9",
            "faultCommandIntervals": [{"status": "OPEN_UNCONFIRMED"}],
            "latestPersisted": {
                "value": 125.4, "observedAt": "2026-11-03T12:26:25+00:00",
                "recordAgeSeconds": 439078.0,
            },
            "windows": [{
                "centerSimulationHours": 1 / 3600,
                "truncated": truncated,
                "samples": [
                    {"simulationTimeHours": 0.0, "value": 10,
                     "temporalRelations": [{"relation": "BEFORE"}]},
                    {"simulationTimeHours": 1 / 3600, "value": 20,
                     "temporalRelations": [{"relation": "DURING_UNCONFIRMED"}]},
                    {"simulationTimeHours": 2 / 3600, "value": 30,
                     "temporalRelations": [{"relation": "DURING_UNCONFIRMED"}]},
                ],
            }],
        }

    def test_boundary_and_descriptive_statistics(self):
        result = analyze(self.evidence())[0]
        self.assertEqual(result["before"]["count"], 1)
        self.assertEqual(result["atOrAfter"]["count"], 2)
        self.assertEqual(result["atOrAfter"]["mean"], 25)
        self.assertEqual(result["meanDifferenceAfterMinusBefore"], 15)
        self.assertEqual(result["relationCounts"]["DURING_UNCONFIRMED"], 2)

    def test_truncation_preserved(self):
        self.assertTrue(analyze(self.evidence(truncated=True))[0]["truncated"])

    def test_no_before_samples_is_not_zero_effect(self):
        evidence = self.evidence()
        evidence["windows"][0]["samples"] = evidence["windows"][0]["samples"][1:]
        result = analyze(evidence)[0]
        self.assertIsNone(result["meanDifferenceAfterMinusBefore"])

    def test_startup_baseline_is_flagged(self):
        baseline = {"count": 12, "mean": 110.3686,
                    "standardDeviation": 33.2774,
                    "minimum": 0.0, "maximum": 120.412}
        quality = assess_baseline(baseline)
        self.assertEqual(quality["status"], "REVIEW_REQUIRED")
        self.assertIn("INSUFFICIENT_PRE_EVENT_SAMPLES", quality["warnings"])
        self.assertIn("HIGH_PRE_EVENT_VARIABILITY", quality["warnings"])
        self.assertIn("POSSIBLE_INITIALIZATION_TRANSIENT", quality["warnings"])

    def test_constant_nonzero_baseline_passes_heuristic(self):
        baseline = {"count": 30, "mean": 125.0,
                    "standardDeviation": 0.01,
                    "minimum": 124.98, "maximum": 125.02}
        self.assertEqual(assess_baseline(baseline)["status"],
                         "HEURISTICALLY_ACCEPTABLE")

    def test_zero_mean_is_not_assumed_stable(self):
        baseline = {"count": 30, "mean": 0.0,
                    "standardDeviation": 0.0,
                    "minimum": 0.0, "maximum": 0.0}
        self.assertIn("BASELINE_VARIABILITY_NOT_ASSESSABLE",
                      assess_baseline(baseline)["warnings"])

    def test_timeline_escapes_untrusted_strings(self):
        evidence = self.evidence()
        evidence["signal"] = "<script>alert(1)</script>"
        report = {"validatedPlan": {"engineering_function": "TI_101"},
                  "temporalEvidence": evidence}
        page = render_html(report)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("<svg", page)
        self.assertIn("not causal", page)


if __name__ == "__main__":
    unittest.main()
