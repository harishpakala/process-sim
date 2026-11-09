"""Offline tests for conservative TEP NEXUS provenance classification."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_provenance_audit import audit, classify_evidence

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
MAPPING = {"function_reference": "F101", "operational_signal": "XMEAS9",
           "asset_uri": "https://example.org/asset/A"}
REGISTRY = {"TI_101": MAPPING}
LIVE = {"candidates": [{"engineering_function": "TI_101",
                        "status": "UNIQUE_PROVISIONAL_CANDIDATE",
                        "mappings": [MAPPING]}], "invalid_rows": []}
COUNTS = {"XMEAS9": {"sampleCount": 12, "minSimulationTimeHours": 0.0,
                     "maxSimulationTimeHours": 1.0}}


class ProvenanceTests(unittest.TestCase):
    def test_provisional_evidence_never_becomes_physical_verification(self):
        report = classify_evidence(REGISTRY, LIVE, COUNTS, RUN)
        self.assertEqual(report["summary"]["status"], "PASS_PROVISIONAL")
        self.assertFalse(report["summary"]["physicalSensorBindingVerified"])
        self.assertFalse(report["summary"]["sharedRunProvenanceVerified"])
        evidence = report["functions"][0]["evidence"]
        self.assertEqual(evidence["physicalSensorBinding"], "NOT_VERIFIED")
        self.assertEqual(evidence["historianRunSignalCooccurrence"], "SOURCE_QUERY_CONFIRMED")

    def test_mapping_drift_requires_review(self):
        changed = {"candidates": [{"engineering_function": "TI_101",
                                   "status": "UNIQUE_PROVISIONAL_CANDIDATE",
                                   "mappings": [{**MAPPING, "operational_signal": "XMEAS8"}]}]}
        report = classify_evidence(REGISTRY, changed, COUNTS, RUN)
        self.assertEqual(report["summary"]["status"], "REVIEW_REQUIRED")

    def test_missing_historian_signal_requires_review(self):
        report = classify_evidence(REGISTRY, LIVE, {}, RUN)
        self.assertEqual(report["summary"]["reviewRequired"], 1)

    def test_ambiguous_mapping_requires_review(self):
        ambiguous = {"candidates": [{"engineering_function": "TI_101",
                                     "status": "AMBIGUOUS_REVIEW_REQUIRED",
                                     "mappings": [MAPPING, {**MAPPING, "asset_uri": "other"}]}]}
        report = classify_evidence(REGISTRY, ambiguous, COUNTS, RUN)
        self.assertEqual(report["summary"]["reviewRequired"], 1)

    def test_audit_uses_read_only_parameterized_sql(self):
        response = MagicMock()
        response.json.return_value = {"results": {"bindings": [{
            "functionId": {"value": "TI_101"},
            "functionRef": {"value": "F101"},
            "signal": {"value": "XMEAS9"},
            "asset": {"value": "https://example.org/asset/A"},
        }]}}
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.fetchall.return_value = [("XMEAS9", 12, 0.0, 1.0)]
        conn = MagicMock()
        conn.__enter__.return_value = conn
        tx = MagicMock()
        tx.__enter__.return_value = tx
        conn.transaction.return_value = tx
        conn.cursor.return_value = cur
        report = audit(RUN, dsn="unused", graphdb_url="unused",
                       registry_loader=lambda *args: REGISTRY,
                       post=lambda *args, **kwargs: response,
                       connect=lambda dsn: conn)
        self.assertEqual(report["summary"]["status"], "PASS_PROVISIONAL")
        conn.execute.assert_called_once_with("SET TRANSACTION READ ONLY")
        self.assertEqual(cur.execute.call_args.args[1], (RUN, ["XMEAS9"]))
        self.assertTrue(report["readOnly"])


if __name__ == "__main__":
    unittest.main()
