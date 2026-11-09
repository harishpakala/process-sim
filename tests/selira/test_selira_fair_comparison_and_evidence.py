"""Regression tests for fail-closed evidence audit and decision policy."""

# Created: 2026-10-30
# Author: Harish
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_selira_evidence import inspect
from selira_shacl_decision_policy import compare, compose


class EvidenceComparisonTests(unittest.TestCase):
    def test_policy_distinguishes_unknown_from_contradiction(self):
        self.assertEqual(compose("V", "U"), "U")
        self.assertEqual(compose("F", "U"), "F")
        self.assertEqual(compose("U", "F"), "F")
        self.assertEqual(compose("F", "NA"), "NA")

    def test_policy_consumer_scope(self):
        findings = {
            "source": {"SC-0" + str(i): "verified" for i in range(1, 6)},
            "consumers": {
                "CAC-01": {"checks": {"coverage": "contradiction"}},
                "CAC-02": {"checks": {"approval": "missing"}},
            },
        }
        result = compare(findings)
        self.assertEqual(result["source"], "V")
        self.assertEqual(result["consumers"]["CAC-01"]["decision"], "F")
        self.assertEqual(result["consumers"]["CAC-02"]["decision"], "U")

    def test_hash_does_not_authenticate_issuer(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            data = b'{"source":"example"}'
            path.write_bytes(data)
            manifest = {"artifacts": [{
                "contract": "SC-01", "path": "record.json",
                "sha256": hashlib.sha256(data).hexdigest(),
                "issuer": "UNVERIFIED CLAIM",
            }]}
            result = inspect(manifest, temp)
            self.assertTrue(result["evidenceAudit"][0]["sha256MatchesManifest"])
            self.assertFalse(result["evidenceAudit"][0]["cryptographicallyAuthenticated"])
            self.assertEqual(result["evidenceAudit"][0]["qualification"], "U")
            self.assertFalse(result["authorization"])

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            result = inspect({"artifacts": [{"path": "../secret.txt"}]}, temp)
            self.assertFalse(result["evidenceAudit"][0]["pathSafe"])


if __name__ == "__main__":
    unittest.main()
