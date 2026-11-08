"""Offline tests for GraphDB assertion provenance checks."""

# Created: 2026-10-29
# Author: Harish
import io
import json
import unittest
from unittest.mock import patch

from process_sim.selira.graph_evidence import check_graph_evidence, fetch_graph_evidence

ASSET = "https://example.org/assetinventory/PI_101"
MATCH = {"graph": "urn:graph:engineering", "reference": "opcua/XMEAS7"}
OTHER = {"graph": "urn:graph:engineering", "reference": "opcua/XMEAS13"}


class GraphEvidenceTests(unittest.TestCase):
    def check(self, rows):
        return check_graph_evidence(
            ASSET, "PI_101", "reactor_pressure", "XMEAS7",
            reader=lambda asset, endpoint=None: rows)

    def test_matching_assertion_is_supported_not_authorized(self):
        result = self.check([MATCH])
        self.assertEqual(result["status"], "supported_graph_and_project_scope")
        self.assertEqual(result["graphAssertions"][0]["graph"], MATCH["graph"])
        self.assertIn("does not grant consumer authorization",
                      result["limitations"][-1])

    def test_missing_assertion_is_unresolved(self):
        self.assertEqual(self.check([])["status"], "unresolved")

    def test_competing_assertion_is_conflicting(self):
        self.assertEqual(self.check([MATCH, OTHER])["status"],
                         "conflicting_graph_assertions")

    def test_invalid_assertion_is_rejected_as_input(self):
        with self.assertRaises(ValueError):
            self.check([{"reference": "opcua/XMEAS7"}])

    def test_wrong_engineering_property_rejected(self):
        result = check_graph_evidence(
            ASSET, "PI_101", "separator_pressure", "XMEAS7",
            reader=lambda asset, endpoint=None: [MATCH])
        self.assertEqual(result["status"], "rejected")

    def test_invalid_asset_iri_rejected_before_reader(self):
        with self.assertRaises(ValueError):
            check_graph_evidence("not-an-iri", "PI_101", "reactor_pressure",
                                 "XMEAS7", reader=lambda **kw: [MATCH])

    def test_graphdb_reader_preserves_named_graph(self):
        payload = {"results": {"bindings": [
            {"g": {"value": MATCH["graph"]},
             "reference": {"value": MATCH["reference"]}}
        ]}}
        with patch("process_sim.selira.graph_evidence.urlopen",
                   return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertEqual(fetch_graph_evidence(ASSET), [MATCH])


if __name__ == "__main__":
    unittest.main()
