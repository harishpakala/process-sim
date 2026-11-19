"""Offline guarded-pipeline tests; the live planner is unaffected."""
import unittest

from process_sim.dtwise.experimental_path_planner import plan_evidenced_path


class ExperimentalPathPlannerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "entities": [
                {"domain": "dexpi", "shape": "urn:Instrument",
                 "properties": ["urn:asset", "urn:localId"]},
                {"domain": "opc", "shape": "urn:Signal",
                 "properties": ["urn:opcAsset", "urn:signalName"]},
            ],
            "shacl_edges": [],
        }
        self.mappings = [{
            "id": "asset-map", "verified": True, "evidence_ids": ["e1"],
            "left_domain": "dexpi", "right_domain": "opc",
            "left_property": "urn:asset", "right_property": "urn:opcAsset",
        }]
        self.calls = []
        self.outputs = [{"node_index": 1, "predicate": "urn:signalName",
                         "as": "signal_name"}]

    def request(self, url, payload, timeout):
        self.calls.append(payload)
        return {"message": {"content": '{"choice":"PATH_0"}'}}

    def plan(self, **kwargs):
        return plan_evidenced_path(
            "Find signal name for instrument", self.catalog,
            kwargs.pop("mappings", self.mappings),
            ("dexpi", "urn:Instrument"), ("opc", "urn:Signal"),
            projections=kwargs.pop("projections", self.outputs),
            request_json=self.request, **kwargs)

    def test_disabled_by_default_and_no_llm_call(self):
        plan, info = self.plan()
        self.assertIsNone(plan)
        self.assertEqual(info["status"], "disabled")
        self.assertFalse(self.calls)

    def test_enabled_binds_selected_verified_path(self):
        plan, info = self.plan(enabled=True)
        self.assertEqual(info["status"], "selected")
        self.assertEqual(plan["edges"][0]["mapping_id"], "asset-map")
        self.assertEqual(plan["projections"][0]["predicate"], "urn:signalName")
        self.assertEqual(len(self.calls), 1)

    def test_unverified_mapping_prevents_model_call(self):
        plan, info = self.plan(enabled=True, mappings=[
            dict(self.mappings[0], verified=False)])
        self.assertIsNone(plan)
        self.assertEqual(info["status"], "no_evidenced_paths")
        self.assertFalse(self.calls)

    def test_invalid_output_owner_fails_closed(self):
        with self.assertRaises(ValueError):
            self.plan(enabled=True, projections=[
                {"node_index": 0, "predicate": "urn:signalName", "as": "x"}])

    def test_filter_preserved(self):
        plan, _ = self.plan(
            enabled=True, filter_spec={"node_index": 0,
                                       "predicate": "urn:localId",
                                       "op": "eq", "value": "FI-001"})
        self.assertEqual(plan["filters"]["value"], "FI-001")
        self.assertEqual(plan["filters"]["entity"], "n0")


if __name__ == "__main__":
    unittest.main()
