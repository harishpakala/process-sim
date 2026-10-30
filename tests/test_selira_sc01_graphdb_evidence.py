import unittest
from process_sim.selira.sc01_graphdb_evidence import assess_graphdb_sc01


class SC01GraphDBEvidenceTests(unittest.TestCase):
    def test_classification_preserves_graph_provenance(self):
        row = {"s": "urn:output", "p": "https://example.org/ecad/isConnectedTo",
               "o": "urn:input", "g": "urn:ecad-graph"}
        report = {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                  "truncated": False, "facts": [row]}
        result = assess_graphdb_sc01(report)
        self.assertEqual(result["status"], "U")
        self.assertFalse(result["authorization"])
        ecad = result["evidence"][1]
        self.assertEqual(ecad["classification"], "EXPLICIT_GRAPH_RELATIONSHIP")
        self.assertEqual(ecad["observations"][0]["graph"], "urn:ecad-graph")

    def test_empty_report_stays_unknown(self):
        result = assess_graphdb_sc01(
            {"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY", "facts": []})
        self.assertEqual(result["status"], "U")
        self.assertTrue(all(x["classification"] == "NOT_OBSERVED"
                            for x in result["evidence"]))

    def test_bad_report_rejected(self):
        with self.assertRaises(ValueError):
            assess_graphdb_sc01({"status": "OTHER", "facts": []})


if __name__ == "__main__":
    unittest.main()
