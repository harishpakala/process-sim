"""Offline tests for the independent semantic-temporal source audit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_correctness_audit import audit

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
MAPPING = {"function_reference": "REF", "operational_signal": "XMEAS9",
           "asset_uri": "https://example.org/asset/9"}
STAMP = "2026-11-08T15:00:00+00:00"


def registry(*args):
    return {"TI_101": MAPPING}


def mapping_reader(*args):
    return dict(MAPPING)


def sample_reader(*args):
    return {"rows": [(30 / 3600, 4.5, STAMP)], "truncated": False}


def virtual_executor(req, **kwargs):
    return {
        "nodes": [
            {"type": "EngineeringFunction", "localId": "TI_101"},
            {"type": "OperationalSignal", "signalId": "XMEAS9"},
            {"type": "EngineeringAsset", "id": MAPPING["asset_uri"]},
            {"type": "SimulationRun", "runId": RUN},
            {"type": "VirtualObservation", "simulationTimeHours": 30 / 3600,
             "value": 4.5, "observedAt": STAMP},
        ],
        "result": {"observationCount": 1, "truncated": False},
        "provenance": {"mappingConfidence": "PROVISIONAL",
                       "physicalSensorBinding": "NOT_VERIFIED",
                       "sharedRunProvenance": "NOT_VERIFIED"},
        "materializedInGraphDB": False,
    }


class AuditTests(unittest.TestCase):
    def kwargs(self):
        return {"dsn": "unused", "graphdb_url": "unused",
                "registry_loader": registry, "mapping_reader": mapping_reader,
                "sample_reader": sample_reader, "virtual_executor": virtual_executor}

    def test_pass(self):
        report = audit(RUN, [[20, 60]], **self.kwargs())
        self.assertEqual(report["summary"]["status"], "PASS")
        self.assertEqual(report["summary"]["passedCases"], 1)

    def test_detects_observation_mismatch(self):
        def wrong(*args):
            return {"rows": [(30 / 3600, 999.0, STAMP)], "truncated": False}
        kw = self.kwargs()
        kw["sample_reader"] = wrong
        report = audit(RUN, [[20, 60]], **kw)
        self.assertEqual(report["summary"]["status"], "FAIL")
        self.assertFalse(report["cases"][0]["checks"]["historian_rows_match_reference"])

    def test_detects_mapping_mismatch(self):
        def wrong(*args):
            return {**MAPPING, "operational_signal": "XMEAS8"}
        kw = self.kwargs()
        kw["mapping_reader"] = wrong
        report = audit(RUN, [[20, 60]], **kw)
        self.assertEqual(report["summary"]["status"], "FAIL")

    def test_error_is_reported(self):
        def broken(*args, **kwargs):
            raise RuntimeError("unavailable")
        kw = self.kwargs()
        kw["virtual_executor"] = broken
        report = audit(RUN, [[20, 60]], **kw)
        self.assertEqual(report["cases"][0]["status"], "ERROR")

    def test_invalid_function_and_bounds(self):
        with self.assertRaises(ValueError):
            audit(RUN, [[20, 60]], functions=["BAD"], **self.kwargs())
        with self.assertRaises(ValueError):
            audit(RUN, [[60, 20]], **self.kwargs())


if __name__ == "__main__":
    unittest.main()
