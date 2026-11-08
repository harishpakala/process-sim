"""Offline GraphDB adapter tests: mocked SPARQL responses, no live server."""

# Created: 2026-10-29
# Author: Harish
import io
import json
import unittest
from unittest.mock import patch

from process_sim.selira.graphdb import (
    fetch_operational_references, resolve_graphdb_correspondence,
)

ASSET = "https://example.org/assetinventory/PI_101"


def response(*references):
    payload = {"results": {"bindings": [
        {"reference": {"type": "literal", "value": ref}} for ref in references
    ]}}
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class GraphDBAdapterTests(unittest.TestCase):
    @patch("process_sim.selira.graphdb.urlopen")
    def test_query_returns_distinct_references(self, urlopen):
        urlopen.return_value.__enter__.return_value = response(
            "opcua/XMEAS7", "opcua/XMEAS7")
        self.assertEqual(fetch_operational_references(ASSET), ["opcua/XMEAS7"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn(b"hasOperationalReference", request.data)

    @patch("process_sim.selira.graphdb.urlopen")
    def test_graphdb_reference_alone_is_not_authoritative(self, urlopen):
        urlopen.return_value.__enter__.return_value = response("opcua/XMEAS7")
        result = resolve_graphdb_correspondence(ASSET, "reactor_pressure")
        self.assertEqual(result.resolution_status, "unresolved")

    @patch("process_sim.selira.graphdb.urlopen")
    def test_competing_graphdb_references_are_ambiguous(self, urlopen):
        urlopen.return_value.__enter__.return_value = response(
            "opcua/XMEAS7", "opcua/XMEAS13")
        result = resolve_graphdb_correspondence(ASSET, "reactor_pressure")
        self.assertEqual(result.resolution_status, "ambiguous")

    @patch("process_sim.selira.graphdb.urlopen")
    def test_explicit_declaration_is_required(self, urlopen):
        urlopen.return_value.__enter__.return_value = response("opcua/XMEAS7")
        declaration = {
            "requestedProperty": "reactor_pressure",
            "signal": "XMEAS7", "reference": "opcua/XMEAS7",
            "validationStatus": "validated",
            "applicabilityStatus": "applicable",
            "evidenceReferences": ["urn:review:pi101"],
        }
        result = resolve_graphdb_correspondence(
            ASSET, "reactor_pressure", declarations=[declaration])
        self.assertEqual(result.resolution_status, "validated")

    def test_rejects_invalid_asset_iri(self):
        with self.assertRaises(ValueError):
            fetch_operational_references("https://example.org/x> ?p ?o")

    @patch("process_sim.selira.graphdb.urlopen", side_effect=OSError("offline"))
    def test_network_failure_is_not_silently_authorized(self, urlopen):
        with self.assertRaises(OSError):
            resolve_graphdb_correspondence(ASSET, "reactor_pressure")


if __name__ == "__main__":
    unittest.main()
