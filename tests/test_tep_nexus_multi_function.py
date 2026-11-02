"""Offline tests for run-scoped registry and generalized planner."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_ollama_query_planner import validate_plan

RUN = "10cfb1d1-2984-4932-8207-dc430ed60c2b"
MAPPING = {"function_reference": "urn:fi", "operational_signal": "XMEAS1", "asset_uri": "urn:asset"}
DISCOVERY = {"mapping_confidence": "PROVISIONAL_NOT_PHYSICALLY_VERIFIED",
             "candidates": [{"engineering_function": "FI_101",
                             "status": "UNIQUE_PROVISIONAL_CANDIDATE", "mappings": [MAPPING]}]}
COVERAGE = {"run_id": RUN, "shared_run_provenance": "NOT_VERIFIED",
            "physical_sensor_binding": "NOT_VERIFIED",
            "functions": [{"engineering_function": "FI_101",
                           "mapping_status": "UNIQUE_PROVISIONAL_CANDIDATE",
                           "temporal_coverage_status": "HAS_SAMPLES",
                           "signals": [{"signal": "XMEAS1", "sample_count": 1201}]}]}


class TestMultiFunctionRegistry(unittest.TestCase):
    def load(self, discovery=None, coverage=None, run=RUN):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            a.write_text(json.dumps(discovery if discovery is not None else DISCOVERY))
            b.write_text(json.dumps(coverage if coverage is not None else COVERAGE))
            return load_supported_functions(a, b, run)

    def test_supported(self):
        self.assertEqual(self.load()["FI_101"], MAPPING)

    def test_wrong_run_rejected(self):
        with self.assertRaises(ValueError):
            self.load(run="another-run")

    def test_no_samples_rejected(self):
        c = json.loads(json.dumps(COVERAGE))
        c["functions"][0]["signals"][0]["sample_count"] = 0
        with self.assertRaises(ValueError):
            self.load(coverage=c)

    def test_mismatched_signal_rejected(self):
        c = json.loads(json.dumps(COVERAGE))
        c["functions"][0]["signals"][0]["signal"] = "XMEAS2"
        with self.assertRaises(ValueError):
            self.load(coverage=c)

    def test_ambiguous_rejected(self):
        d = json.loads(json.dumps(DISCOVERY))
        d["candidates"][0]["status"] = "AMBIGUOUS_REVIEW_REQUIRED"
        with self.assertRaises(ValueError):
            self.load(discovery=d)

    def test_other_function_plan_accepted(self):
        plan = dict(intent="latest_and_history", engineering_function="FI_101",
                    history_window_minutes=10, include_asset=True, include_provenance=True)
        self.assertEqual(validate_plan(plan, "Show FI_101 over the last 10 minutes.",
                                       {"FI_101": MAPPING})["engineering_function"], "FI_101")

    def test_unlisted_function_plan_rejected(self):
        plan = dict(intent="latest", engineering_function="FI_999",
                    history_window_minutes=10, include_asset=False, include_provenance=False)
        with self.assertRaises(ValueError):
            validate_plan(plan, "Show FI_999", {"FI_101": MAPPING})

    @patch("tep_nexus_function_registry.requests.post")
    def test_live_mapping_resolves(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {"results": {"bindings": [{
            "functionId": {"value": "FI_101"}, "functionRef": {"value": "urn:fi"},
            "signal": {"value": "XMEAS1"}, "asset": {"value": "urn:asset"}
        }]}}
        self.assertEqual(resolve_supported_mapping("http://graphdb", "FI_101",
                         {"FI_101": MAPPING})["operational_signal"], "XMEAS1")

    @patch("tep_nexus_function_registry.requests.post")
    def test_live_mapping_change_rejected(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {"results": {"bindings": [{
            "functionId": {"value": "FI_101"}, "functionRef": {"value": "urn:fi"},
            "signal": {"value": "XMEAS2"}, "asset": {"value": "urn:asset"}
        }]}}
        with self.assertRaises(RuntimeError):
            resolve_supported_mapping("http://graphdb", "FI_101", {"FI_101": MAPPING})


if __name__ == "__main__":
    unittest.main()
