"""Offline tests for opt-in Phase 3 AND filters."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_phase3_and import (
    run_phase3_and_plan, compile_phase3_and_sparql,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


@pytest.fixture
def sample():
    root, device, endpoint = "urn:ECAD", "urn:Device", "urn:EndPoint"
    e0 = {"from": root, "to": device, "predicate": "https://example.org/hasDevice",
          "property_shape": "urn:DeviceLink"}
    e1 = {"from": device, "to": endpoint, "predicate": "https://example.org/hasEndPoint",
          "property_shape": "urn:EndPointLink"}
    device_id = {"owner": device, "predicate": "https://example.org/localId",
                 "property_shape": "urn:DeviceId", "name": "LocalId"}
    endpoint_id = {"owner": endpoint, "predicate": "https://example.org/localId",
                   "property_shape": "urn:EndPointId", "name": "LocalId"}
    address = {"owner": endpoint, "predicate": "https://example.org/address",
               "property_shape": "urn:Address", "name": "Address"}
    index = SubgraphIndex("ecad", {root: {"labels": ["ECAD"]},
                                    device: {"labels": ["Device"]},
                                    endpoint: {"labels": ["EndPoint"]}},
                          {device: [device_id], endpoint: [endpoint_id, address]},
                          [e0, e1])
    candidates = [(device_id, [root, device], [e0]),
                  (endpoint_id, [root, device, endpoint], [e0, e1]),
                  (address, [root, device, endpoint], [e0, e1])]
    prepared = {"prompt": {"domain": "ecad",
                 "question": "Show Address of EndPoint belonging to Device where Device LocalId = FI_101 and EndPoint LocalId = EP_202 in ECAD",
                 "candidates": [{"id": f"C{i}", "path": str(i)}
                                for i in range(1, 4)]},
                "registry": {f"C{i}": {"property": prop, "node_uris": nodes, "edges": edges}
                             for i, (prop, nodes, edges) in enumerate(candidates, 1)}}
    qualified = qualify_candidates(index, prepared)
    ids = {c["path"]: c["id"] for c in qualified["prompt"]["candidates"]
           if c["kind"] == "property"}
    plan = {"status": "selected",
            "result_id": ids["ECAD → Device → EndPoint → Address"],
            "result_meaning": "EndPoint.Address",
            "filters": [
                {"filter_id": ids["ECAD → Device → LocalId"], "owner": "Device", "property": "LocalId", "operator": "=", "value": "FI_101"},
                {"filter_id": ids["ECAD → Device → EndPoint → LocalId"], "owner": "EndPoint", "property": "LocalId", "operator": "=", "value": "EP_202"},
            ], "reason": "Both filters belong to result path"}
    return index, prepared, plan


def transport(plan):
    def reply(url, payload, timeout):
        return {"message": {"content": json.dumps(plan)}}
    return reply


def test_two_filters_attach_to_distinct_owner_nodes(sample):
    index, prepared, plan = sample
    result = run_phase3_and_plan(index, prepared, transport=transport(plan))
    sparql = compile_phase3_and_sparql(result)
    assert result["plan"]["status"] == "selected"
    assert "?n1 <https://example.org/localId> ?filterValue1 ." in sparql
    assert "?n2 <https://example.org/localId> ?filterValue2 ." in sparql
    assert 'FILTER(?filterValue1 = "FI_101")' in sparql
    assert 'FILTER(?filterValue2 = "EP_202")' in sparql
    assert "\\n" not in sparql


def test_invented_literal_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][1]["value"] = "invented"
    with pytest.raises(SelectionContractError, match="values"):
        run_phase3_and_plan(index, prepared, transport=transport(plan))


def test_descendant_filter_rejected(sample):
    index, prepared, plan = sample
    plan["result_id"] = plan["filters"][0]["filter_id"]
    plan["result_meaning"] = "Device.LocalId"
    with pytest.raises(SelectionContractError, match="Filter owner"):
        run_phase3_and_plan(index, prepared, transport=transport(plan))


def test_or_skips_model(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = prepared["prompt"]["question"].replace(" and EndPoint", " or EndPoint")
    result = run_phase3_and_plan(index, prepared, transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase3_and_sparql(result) is None


def test_single_filter_skips_model(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = "Show Address where Device LocalId = FI_101"
    result = run_phase3_and_plan(index, prepared, transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"


def test_duplicate_filters_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][1] = dict(plan["filters"][0])
    with pytest.raises(SelectionContractError, match="Duplicate"):
        run_phase3_and_plan(index, prepared, transport=transport(plan))


def test_mismatched_result_interpretation_rejected(sample):
    index, prepared, plan = sample
    plan["result_meaning"] = "PLCEndPoint.Address"
    with pytest.raises(SelectionContractError, match="Result interpretation"):
        run_phase3_and_plan(index, prepared, transport=transport(plan))


def test_mismatched_filter_interpretation_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][0]["owner"] = "EndPoint"
    with pytest.raises(SelectionContractError, match="Filter interpretation"):
        run_phase3_and_plan(index, prepared, transport=transport(plan))
