"""Offline regression tests for the grounded fault-relative explanation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_grounded_explanation import build_facts, deterministic_answer, generate, _screen_llm


def fixtures():
    query = {
        "question": "Show TI_101 measurements around fault injection",
        "validatedPlan": {"engineering_function": "TI_101"},
        "engineeringMapping": {"operational_signal": "XMEAS9"},
        "provenance": {"mappingConfidence": "PROVISIONAL",
                       "physicalSensorBinding": "NOT_VERIFIED"},
        "temporalEvidence": {
            "runId": "test-run", "signal": "XMEAS9",
            "faultCommands": [{"action": "inject"}],
            "faultCommandIntervals": [{"status": "OPEN_UNCONFIRMED"}],
            "latestPersisted": {"observedAt": "2026-11-08T15:17:13+00:00",
                                "value": 125.4, "recordAgeSeconds": 2.777},
            "windows": [{"centerSimulationHours": 0.01,
                         "samples": [{"value": 120}, {"value": 125}]}],
        },
    }
    analysis = [{
        "centerSimulationHours": 0.01, "centerSimulationSeconds": 36.0,
        "sampleCount": 2, "truncated": False,
        "before": {"count": 1, "mean": 120.0},
        "atOrAfter": {"count": 1, "mean": 125.0},
        "meanDifferenceAfterMinusBefore": 5.0,
        "baselineQuality": {"status": "REVIEW_REQUIRED",
                            "warnings": ["INSUFFICIENT_PRE_EVENT_SAMPLES"]},
        "relationCounts": {"BEFORE": 1, "DURING_UNCONFIRMED": 1},
    }]
    return query, analysis


class GroundedExplanationTests(unittest.TestCase):
    def test_deterministic_output_preserves_caveats(self):
        facts = build_facts(*fixtures())
        answer = deterministic_answer(facts)
        for term in ("REVIEW_REQUIRED", "INSUFFICIENT_PRE_EVENT_SAMPLES",
                     "OPEN_UNCONFIRMED", "NOT_VERIFIED", "not causal",
                     "TI_101", "XMEAS9"):
            self.assertIn(term, answer)

    def test_rejects_mismatched_mapping(self):
        query, analysis = fixtures()
        query["engineeringMapping"]["operational_signal"] = "XMEAS8"
        with self.assertRaises(ValueError):
            build_facts(query, analysis)

    def test_rejects_stale_analysis(self):
        query, analysis = fixtures()
        analysis[0]["sampleCount"] = 3
        with self.assertRaises(ValueError):
            build_facts(query, analysis)

    def test_rejects_missing_warning(self):
        facts = build_facts(*fixtures())
        answer = deterministic_answer(facts).replace(
            "INSUFFICIENT_PRE_EVENT_SAMPLES", "none")
        self.assertFalse(_screen_llm(answer, facts)[0])

    def test_rejects_invented_number(self):
        facts = build_facts(*fixtures())
        self.assertFalse(_screen_llm(deterministic_answer(facts) +
                                     " Additional effect 999999.", facts)[0])

    def test_offline_mode_never_contacts_ollama(self):
        with patch("tep_nexus_grounded_explanation.requests.post") as post:
            result = generate(*fixtures(), ollama_url=None)
            post.assert_not_called()
        self.assertEqual(result["status"], "DETERMINISTIC_ONLY")
        self.assertEqual(result["ollama"]["status"], "NOT_REQUESTED")

    def test_ollama_failure_preserves_deterministic_answer(self):
        with patch("tep_nexus_grounded_explanation.explain_with_ollama",
                   side_effect=ValueError("invalid response")):
            result = generate(*fixtures(), ollama_url="http://localhost:11434")
        self.assertEqual(result["ollama"]["status"], "ERROR")
        self.assertIn("REVIEW_REQUIRED", result["answer"])


if __name__ == "__main__":
    unittest.main()
