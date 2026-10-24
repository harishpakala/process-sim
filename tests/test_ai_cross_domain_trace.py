"""Offline evidence tests for asset/catalog/temporal traceability."""
import unittest
from process_sim.ai.cross_domain_trace import validate_trace_plan, execute_trace_plan

RUN = "c2e5a121-99f8-4d19-b0b5-15cefe5bd611"

def specs(asset, endpoint):
    return {"assetIri": "https://example.org/asset/7",
            "linkStatus": "linked", "productReference": "SMC_PSE550",
            "product": {"iri": "https://example.org/product/7"},
            "technicalSpecifications": [{
                "iri": "https://example.org/spec/pressure",
                "name": "OperatingPressure", "value": "-50 to 50 kPa",
                "semanticIds": [], "supplementalSemanticIds": []}]}

class CrossDomainTests(unittest.TestCase):
    def test_catalog_does_not_infer_limits(self):
        result = execute_trace_plan({"operation": "asset_trace", "assetId": "TEP_XMEAS7"},
                                    "graph", specs_reader=specs)
        self.assertEqual(result["comparisonStatus"], "not_validated")
        self.assertEqual(result["catalogProperties"][0]["catalogValue"], "-50 to 50 kPa")
        self.assertEqual(result["catalogProperties"][0]["semanticIds"], [])

    def test_ambiguous_signal_preserves_evidence(self):
        result = execute_trace_plan(
            {"operation": "asset_trace", "assetId": "TEP_XMEAS7",
             "runId": RUN, "limit": 10}, "graph", specs_reader=specs,
            history_reader=lambda asset, run, limit: {
                "status": "ambiguous", "references": ["XMEAS7", "XMEAS8"],
                "signals": ["XMEAS7", "XMEAS8"]})
        self.assertEqual(result["historyStatus"], "ambiguous")
        self.assertEqual(result["operationalEvidence"]["points"], [])
        self.assertEqual(result["comparisonStatus"], "not_validated")

    def test_rejects_invalid_plan(self):
        with self.assertRaises(ValueError):
            validate_trace_plan({"operation": "asset_trace", "assetId": "x",
                                 "runId": RUN})
