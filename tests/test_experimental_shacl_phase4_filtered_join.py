"""Offline Phase 4.2 same-Device filtered-join tests."""
import json
import pytest

from process_sim.dtwise.experimental_shacl_phase4_filtered_join import (
    run_phase4_filtered_join_plan, compile_phase4_filtered_join_sparql,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


@pytest.fixture
def sample():
    root, dev, ep, plc = "urn:ECAD", "urn:Device", "urn:EndPoint", "urn:PLCEndPoint"
    e0 = dict(from_=root, to=dev, predicate="urn:hasDevice", property_shape="urn:e0")
    e0["from"] = e0.pop("from_")
    e1 = {"from": dev, "to": ep, "predicate": "urn:hasEndPoint", "property_shape": "urn:e1"}
    e2 = {"from": dev, "to": plc, "predicate": "urn:hasPLCEndPoint", "property_shape": "urn:e2"}
    p1 = {"owner": ep, "predicate": "urn:hasAddress", "property_shape": "urn:p1", "name": "Address"}
    p2 = {"owner": plc, "predicate": "urn:hasAddress", "property_shape": "urn:p2", "name": "Address"}
    pf = {"owner": dev, "predicate": "urn:hasLocalId", "property_shape": "urn:pf", "name": "LocalId"}
    index = SubgraphIndex("ecad", {root: {"labels": ["ECAD"]}, dev: {"labels": ["Device"]},
                                   ep: {"labels": ["EndPoint"]}, plc: {"labels": ["PLCEndPoint"]}},
                          {ep: [p1], plc: [p2], dev: [pf]}, [e0, e1, e2])
    question = ("Show EndPoint Address and PLCEndPoint Address belonging to the same "
                "Device where Device LocalId = FI_101 in ECAD.")
    data = [(p1, [root, dev, ep], [e0, e1]),
            (p2, [root, dev, plc], [e0, e2]), (pf, [root, dev], [e0])]
    prepared = {"prompt": {"domain": "ecad", "question": question,
                           "candidates": [{"id": f"C{i}", "path": str(i)}
                                          for i in range(1, 4)]},
                "registry": {f"C{i}": {"property": p, "node_uris": n, "edges": e}
                             for i, (p, n, e) in enumerate(data, 1)}}
    q = qualify_candidates(index, prepared)
    ids = {c["path"]: c["id"] for c in q["prompt"]["candidates"] if c["kind"] == "property"}
    plan = {"status": "selected", "result_ids": [
        ids["ECAD → Device → EndPoint → Address"],
        ids["ECAD → Device → PLCEndPoint → Address"]],
        "join_owner": "Device", "filter_id": ids["ECAD → Device → LocalId"],
        "filter_owner": "Device", "filter_property": "LocalId",
        "operator": "=", "value": "FI_101", "reason": "Verified shared Device filter"}
    return index, prepared, plan


def transport(plan):
    return lambda *_: {"message": {"content": json.dumps(plan)}}


def test_one_join_with_device_filter(sample):
    index, prepared, plan = sample
    result = run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))
    query = compile_phase4_filtered_join_sparql(result)
    assert result["plan"]["status"] == "selected"
    assert query.count("?device <urn:hasLocalId> ?filterValue .") == 1
    assert 'FILTER(?filterValue = "FI_101")' in query
    assert query.count("?ecad <urn:hasDevice> ?device .") == 1
    assert "?device <urn:hasEndPoint> ?endpoint ." in query
    assert "?device <urn:hasPLCEndPoint> ?plcEndpoint ." in query


def test_invented_literal_rejected(sample):
    index, prepared, plan = sample
    plan["value"] = "invented"
    with pytest.raises(SelectionContractError, match="literal"):
        run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))


def test_wrong_filter_id_rejected(sample):
    index, prepared, plan = sample
    plan["filter_id"] = plan["result_ids"][0]
    with pytest.raises(SelectionContractError, match="semantic grounding"):
        run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))


def test_wrong_filter_owner_rejected(sample):
    index, prepared, plan = sample
    plan["filter_owner"] = "EndPoint"
    with pytest.raises(SelectionContractError, match="interpretation"):
        run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))


def test_missing_branch_rejected(sample):
    index, prepared, plan = sample
    plan["result_ids"] = plan["result_ids"][:1]
    with pytest.raises(SelectionContractError, match="two distinct"):
        run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))


@pytest.mark.parametrize("question", [
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device in ECAD",
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device where EndPoint LocalId = FI_101 in ECAD",
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device where Device LocalId = FI_101 or FI_102 in ECAD",
])
def test_unsupported_abstains_before_model(sample, question):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = question
    result = run_phase4_filtered_join_plan(index, prepared,
        transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase4_filtered_join_sparql(result) is None


def test_quoted_literal_supported(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = prepared["prompt"]["question"].replace(
        "FI_101", '"FI_101"')
    result = run_phase4_filtered_join_plan(index, prepared, transport=transport(plan))
    assert 'FILTER(?filterValue = "FI_101")' in compile_phase4_filtered_join_sparql(result)
