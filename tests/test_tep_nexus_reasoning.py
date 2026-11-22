"""Regression tests for query-scoped R01-R03 reasoning; no databases needed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_reasoning import reason


def fixture(cross_domain=True):
    nodes = [
        {"id": "f1", "type": "EngineeringFunction", "domain": "DEXPI", "localId": "FI_101"},
        {"id": "s", "type": "OperationalSignal", "signalId": "XMEAS1"},
        {"id": "r", "type": "SimulationRun", "runId": "run-1"},
        {"id": "a", "type": "AssetIdentifier", "identifier": "asset-1"},
        {"id": "o", "type": "VirtualObservation", "simulationTimeHours": 1.0,
         "value": 12.0, "observedAt": "2026-11-22T10:00:00+00:00"},
    ]
    edges = [
        {"source": "f1", "predicate": "mapsToSignal", "target": "s"},
        {"source": "f1", "predicate": "hasAssetIdentifier", "target": "a"},
        {"source": "r", "predicate": "hasSignal", "target": "s"},
        {"source": "o", "predicate": "observesSignal", "target": "s"},
        {"source": "o", "predicate": "belongsToRun", "target": "r"},
    ]
    if cross_domain:
        nodes.append({"id": "f2", "type": "EngineeringFunction", "domain": "ECAD", "localId": "FI-1101"})
        edges.extend([
            {"source": "f2", "predicate": "mapsToSignal", "target": "s"},
            {"source": "f2", "predicate": "hasAssetIdentifier", "target": "a"},
        ])
    return {"nodes": nodes, "edges": edges}


class ReasoningTests(unittest.TestCase):
    def test_r01_r02_r03_with_cross_domain_mapping(self):
        output = reason(fixture(), domain="DEXPI", engineering_function="FI_101",
                        run_id="run-1", expected_count=1)
        self.assertEqual(output["R01"]["observationCount"], 1)
        self.assertEqual(len(output["R01"]["observations"][0]["path"]), 2)
        self.assertEqual(len(output["R02"]["engineeringFunctions"]), 2)
        self.assertEqual(output["R03"]["status"], "complete")
        self.assertEqual(output["R04"]["status"], "insufficient_evidence")

    def test_r04_balanced_windows_and_r05_exact_target(self):
        graph = fixture()
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "o"]
        graph["edges"] = [e for e in graph["edges"] if e["source"] != "o"]
        for identifier, seconds, value in (
            ("b1", 40, 8.0), ("b2", 43, 10.0),
            ("a1", 49, 12.0), ("a2", 52, 14.0),
            ("outside", 5, 1000.0),
        ):
            graph["nodes"].append({"id": identifier, "type": "VirtualObservation",
                                   "simulationTimeHours": seconds / 3600,
                                   "value": value, "observedAt": "2026-11-22T10:00:00+00:00"})
            graph["edges"].extend([
                {"source": identifier, "predicate": "observesSignal", "target": "s"},
                {"source": identifier, "predicate": "belongsToRun", "target": "r"},
            ])
        graph["nodes"].append({"id": "cmd", "type": "RecordedFaultCommand",
                               "eventId": "event-1", "action": "inject",
                               "target": "XMEAS1", "faultId": "f-1",
                               "simulationTimeHours": 46 / 3600})
        graph["edges"].append({"source": "r", "predicate": "hasRecordedCommand", "target": "cmd"})
        result = reason(graph, domain="DEXPI", engineering_function="FI_101",
                        run_id="run-1", expected_count=5)
        event = result["R04"]["events"][0]
        self.assertEqual(result["R04"]["status"], "complete")
        self.assertEqual(event["beforeCount"], 2)
        self.assertEqual(event["afterCount"], 2)
        self.assertEqual(event["beforeMean"], 9.0)
        self.assertEqual(event["afterMean"], 13.0)
        self.assertEqual(event["relevance"], "target_verified")
        self.assertEqual(result["R05"]["status"], "complete")
        graph["nodes"][-1]["target"] = "XMEAS99"
        unrelated = reason(graph, domain="DEXPI", engineering_function="FI_101",
                           run_id="run-1", expected_count=5)
        self.assertEqual(unrelated["R04"]["status"], "complete")
        self.assertEqual(unrelated["R05"]["status"], "insufficient_evidence")
        self.assertEqual(unrelated["R04"]["events"][0]["relevance"], "target_unverified")
        graph["nodes"][-1]["target"] = None
        missing = reason(graph, domain="DEXPI", engineering_function="FI_101",
                         run_id="run-1", expected_count=5)
        self.assertEqual(missing["R05"]["status"], "insufficient_evidence")

    def test_r04_requires_both_sides_of_command(self):
        graph = fixture()
        graph["nodes"].append({"id": "cmd", "type": "RecordedFaultCommand",
                               "eventId": "event-2", "action": "set",
                               "simulationTimeHours": 2.0})
        graph["edges"].append({"source": "r", "predicate": "hasRecordedCommand", "target": "cmd"})
        result = reason(graph, domain="DEXPI", engineering_function="FI_101",
                        run_id="run-1", expected_count=1)
        self.assertEqual(result["R04"]["status"], "insufficient_evidence")
        self.assertEqual(result["R05"]["status"], "insufficient_evidence")

    def test_r03_requires_both_domains(self):
        output = reason(fixture(False), domain="DEXPI", engineering_function="FI_101",
                        run_id="run-1", expected_count=1)
        self.assertEqual(output["R03"]["status"], "insufficient_evidence")

    def test_missing_observation_edge_is_not_silent(self):
        graph = fixture()
        graph["edges"] = [e for e in graph["edges"] if e["predicate"] != "belongsToRun"]
        with self.assertRaisesRegex(ValueError, "count differs"):
            reason(graph, domain="DEXPI", engineering_function="FI_101",
                   run_id="run-1", expected_count=1)

    def test_missing_graph_node_is_rejected(self):
        graph = fixture()
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "s"]
        with self.assertRaisesRegex(ValueError, "missing node"):
            reason(graph, domain="DEXPI", engineering_function="FI_101",
                   run_id="run-1", expected_count=1)


if __name__ == "__main__":
    unittest.main()
