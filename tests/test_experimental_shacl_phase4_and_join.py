"""Offline regression tests for opt-in Phase 4.3 AND filtered sibling join."""
import json
import pytest
from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    run_phase4_and_join_plan, compile_phase4_and_join_sparql,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex

@pytest.fixture
def sample():
    root, dev, ep, plc = "urn:ECAD", "urn:Device", "urn:EndPoint", "urn:PLCEndPoint"
    e0 = dict(from_=root, to=dev, predicate="https://example.org/ecad/hasDevice", property_shape="urn:e0")
    e0["from"] = e0.pop("from_")
    e1 = {"from": dev, "to": ep, "predicate": "https://example.org/ecad/hasEndPoint", "property_shape": "urn:e1"}
    e2 = {"from": dev, "to": plc, "predicate": "https://example.org/ecad/hasPLCEndPoint", "property_shape": "urn:e2"}
    p1 = {"owner": ep, "predicate": "https://example.org/ecad/hasAddress", "property_shape": "urn:p1", "name": "Address"}
    p2 = {"owner": plc, "predicate": "https://example.org/ecad/hasAddress", "property_shape": "urn:p2", "name": "Address"}
    pf = {"owner": dev, "predicate": "https://example.org/ecad/hasLocalId", "property_shape": "urn:pf", "name": "LocalId"}
    pt = {"owner": dev, "predicate": "https://example.org/ecad/hasDeviceType", "property_shape": "urn:pt", "name": "DeviceType"}
    index = SubgraphIndex("ecad", {root: {"labels": ["ECAD"]}, dev: {"labels": ["Device"]},
                                   ep: {"labels": ["EndPoint"]}, plc: {"labels": ["PLCEndPoint"]}},
                          {ep: [p1], plc: [p2], dev: [pf, pt]}, [e0, e1, e2])
    question = ("Show EndPoint Address and PLCEndPoint Address belonging to the same "
                "Device where Device LocalId = FI_101 and Device DeviceType = Sensor in ECAD.")
    data = [(p1, [root, dev, ep], [e0, e1]),
            (p2, [root, dev, plc], [e0, e2]), (pf, [root, dev], [e0]), (pt, [root, dev], [e0])]
    prepared = {"prompt": {"domain": "ecad", "question": question,
                           "candidates": [{"id": f"C{i}", "path": str(i)}
                                          for i in range(1, 5)]},
                "registry": {f"C{i}": {"property": p, "node_uris": n, "edges": e}
                             for i, (p, n, e) in enumerate(data, 1)}}
    q = qualify_candidates(index, prepared)
    ids = {c["path"]: c["id"] for c in q["prompt"]["candidates"] if c["kind"] == "property"}
    plan = {"status": "selected", "result_ids": [
        ids["ECAD → Device → EndPoint → Address"],
        ids["ECAD → Device → PLCEndPoint → Address"]],
        "join_owner": "Device", "filters": [
            {"filter_id": ids["ECAD → Device → LocalId"], "owner": "Device",
             "property": "LocalId", "operator": "=", "value": "FI_101"},
            {"filter_id": ids["ECAD → Device → DeviceType"], "owner": "Device",
             "property": "DeviceType", "operator": "=", "value": "Sensor"}],
        "reason": "Verified shared Device filters"}
    return index, prepared, plan



def transport(plan):
    return lambda *_: {"message": {"content": json.dumps(plan)}}


def test_two_filters_one_join(sample):
    index, prepared, plan = sample
    result = run_phase4_and_join_plan(index, prepared, transport=transport(plan))
    query = compile_phase4_and_join_sparql(result)
    assert result["plan"]["status"] == "selected"
    assert query.count("?ecad <https://example.org/ecad/hasDevice> ?device .") == 1
    assert "?device <https://example.org/ecad/hasEndPoint> ?endpoint ." in query
    assert "?device <https://example.org/ecad/hasPLCEndPoint> ?plcEndpoint ." in query
    assert 'FILTER(?filterValue1 = "FI_101")' in query
    assert 'FILTER(?filterValue2 = "Sensor")' in query
    assert query.count("FILTER(") == 2


def test_fabricated_value_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][1]["value"] = "Actuator"
    with pytest.raises(SelectionContractError, match="literals"):
        run_phase4_and_join_plan(index, prepared, transport=transport(plan))


def test_wrong_filter_owner_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][1]["owner"] = "EndPoint"
    with pytest.raises(SelectionContractError, match="semantic grounding"):
        run_phase4_and_join_plan(index, prepared, transport=transport(plan))


def test_wrong_filter_id_rejected(sample):
    index, prepared, plan = sample
    plan["filters"][1]["filter_id"] = plan["filters"][0]["filter_id"]
    with pytest.raises(SelectionContractError, match="semantic grounding"):
        run_phase4_and_join_plan(index, prepared, transport=transport(plan))


def test_missing_result_rejected(sample):
    index, prepared, plan = sample
    plan["result_ids"] = plan["result_ids"][:1]
    with pytest.raises(SelectionContractError, match="two distinct"):
        run_phase4_and_join_plan(index, prepared, transport=transport(plan))


def test_swapped_filter_order_rejected(sample):
    index, prepared, plan = sample
    plan["filters"].reverse()
    with pytest.raises(SelectionContractError, match="semantic grounding"):
        run_phase4_and_join_plan(index, prepared, transport=transport(plan))


@pytest.mark.parametrize("question", [
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device in ECAD",
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device where Device LocalId = FI_101 in ECAD",
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device where Device LocalId = FI_101 or Device DeviceType = Sensor in ECAD",
    "Show EndPoint Address and PLCEndPoint Address belonging to the same Device where Device LocalId = FI_101 and EndPoint DeviceType = Sensor in ECAD",
])
def test_unsupported_abstains_without_model(sample, question):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = question
    result = run_phase4_and_join_plan(index, prepared,
        transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase4_and_join_sparql(result) is None


def test_quoted_values(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = prepared["prompt"]["question"].replace(
        "FI_101", '"FI_101"').replace("Sensor", "'Sensor'")
    result = run_phase4_and_join_plan(index, prepared, transport=transport(plan))
    assert 'FILTER(?filterValue2 = "Sensor")' in compile_phase4_and_join_sparql(result)


# Phase 5.3: alternate phrasing, still subject to full SHACL validation.
def test_alternate_question_compiles_same_join(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = (
        "Find the addresses of EndPoint and PLCEndPoint for devices "
        "with LocalId FI_101 and DeviceType Sensor")
    result = run_phase4_and_join_plan(index, prepared, transport=transport(plan))
    query = compile_phase4_and_join_sparql(result)
    assert result["plan"]["status"] == "selected"
    assert query.count("FILTER(") == 2
    assert 'FILTER(?filterValue1 = "FI_101")' in query
    assert 'FILTER(?filterValue2 = "Sensor")' in query


@pytest.mark.parametrize("question", [
    "Find the addresses of EndPoint and PLCEndPoint for devices with LocalId FI_101 or DeviceType Sensor",
    "Find the addresses of EndPoint and PLCEndPoint for devices with LocalId FI_101",
    "Find the addresses of EndPoint and PLCEndPoint for devices with LocalId FI_101 and DeviceType Sensor and Status Active",
    "Find the addresses of EndPoint and PLCEndPoint for devices with LocalId FI_101 and DeviceType Sensor in DEXPI",
])
def test_alternate_unsupported_abstains(sample, question):
    index, prepared, _ = sample
    prepared["prompt"]["question"] = question
    result = run_phase4_and_join_plan(
        index, prepared, transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase4_and_join_sparql(result) is None


# Phase 5.4 structured intent is derived only from independently verified plans.
def test_selected_plan_has_verified_structured_intent(sample):
    index, prepared, plan = sample
    result = run_phase4_and_join_plan(index, prepared, transport=transport(plan))
    intent = result["intent"]
    assert intent["domain"] == "ecad"
    assert intent["operation"] == "select"
    assert intent["result_property_ids"] == plan["result_ids"]
    assert intent["join"] == {"kind": "shared_ancestor", "owner": "Device"}
    assert intent["boolean_operator"] == "and"
    assert [f["value"] for f in intent["filters"]] == ["FI_101", "Sensor"]
    assert [f["property_id"] for f in intent["filters"]] == [
        f["filter_id"] for f in plan["filters"]]


def test_unresolved_plan_has_no_intent(sample):
    index, prepared, _ = sample
    prepared["prompt"]["question"] = "Show Address"
    result = run_phase4_and_join_plan(
        index, prepared, transport=lambda *_: pytest.fail("Model must not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert result["intent"] is None


def test_intent_rejects_fabricated_filter_value(sample):
    from process_sim.dtwise.experimental_shacl_query_intent import validated_join_intent
    index, prepared, plan = sample
    qualified = qualify_candidates(index, prepared)
    plan["filters"][0]["value"] = "FI_999"
    with pytest.raises(SelectionContractError, match="contradict"):
        validated_join_intent(plan, qualified)


# Phase 5.4 direct model-proposed intent: offline, no Ollama required.
def _direct_intent(plan):
    return {
        "domain": "ecad", "operation": "select",
        "result_property_ids": plan["result_ids"],
        "join": {"kind": "shared_ancestor", "owner": "Device"},
        "boolean_operator": "and",
        "filters": [
            {"property_id": f["filter_id"], "owner": f["owner"],
             "property": f["property"], "operator": f["operator"],
             "value": f["value"]}
            for f in plan["filters"]
        ],
    }


def test_direct_intent_compiles_only_after_validation(sample):
    from process_sim.dtwise.experimental_shacl_query_intent import run_direct_join_intent
    index, prepared, plan = sample
    proposal = _direct_intent(plan)
    result = run_direct_join_intent(
        index, prepared, transport=transport(proposal))
    assert result["intent"] == proposal
    assert result["sparql"].count("FILTER(") == 2
    assert 'FILTER(?filterValue1 = "FI_101")' in result["sparql"]


@pytest.mark.parametrize("change", [
    lambda x: x.update(domain="dexpi"),
    lambda x: x.update(operation="delete"),
    lambda x: x.update(boolean_operator="or"),
    lambda x: x["join"].update(owner="EndPoint"),
    lambda x: x["result_property_ids"].__setitem__(0, "P999"),
    lambda x: x["filters"][0].update(value="FI_999"),
    lambda x: x["filters"][1].update(operator="!="),
    lambda x: x["filters"][1].update(owner="EndPoint"),
    lambda x: x.update(extra="unexpected"),
])
def test_direct_intent_rejects_unverified_proposal(sample, change):
    from process_sim.dtwise.experimental_shacl_query_intent import (
        validate_proposed_join_intent,
    )
    index, prepared, plan = sample
    proposal = _direct_intent(plan)
    change(proposal)
    with pytest.raises(SelectionContractError):
        validate_proposed_join_intent(proposal, qualify_candidates(index, prepared))


def test_direct_intent_unsupported_question_skips_model(sample):
    from process_sim.dtwise.experimental_shacl_query_intent import run_direct_join_intent
    index, prepared, _ = sample
    prepared["prompt"]["question"] = "Find all addresses"
    result = run_direct_join_intent(
        index, prepared, transport=lambda *_: pytest.fail("Must not call model"))
    assert result["intent"] is None
    assert result["sparql"] is None


# Phase 5.5: schema-only validation; question entailment is a separate gate.
def test_schema_intent_accepts_one_or_two_ancestor_filters(sample):
    from process_sim.dtwise.experimental_shacl_schema_intent import validate_schema_join_intent
    index, prepared, plan = sample
    qualified = qualify_candidates(index, prepared)
    intent = _direct_intent(plan)
    assert validate_schema_join_intent(intent, qualified) is intent
    intent["filters"] = intent["filters"][:1]
    assert validate_schema_join_intent(intent, qualified) is intent


@pytest.mark.parametrize("change", [
    lambda x: x.update(domain="dexpi"),
    lambda x: x.update(operation="delete"),
    lambda x: x["join"].update(owner="EndPoint"),
    lambda x: x["filters"][0].update(property_id="P999"),
    lambda x: x["filters"][0].update(operator="!="),
    lambda x: x["filters"][0].update(owner="EndPoint"),
    lambda x: x["filters"][0].update(property="DeviceType"),
    lambda x: x.update(boolean_operator="or"),
    lambda x: x["filters"].append(dict(x["filters"][0])),
    lambda x: x["result_property_ids"].__setitem__(1, x["result_property_ids"][0]),
])
def test_schema_intent_rejects_invalid_graph_structure(sample, change):
    from process_sim.dtwise.experimental_shacl_schema_intent import validate_schema_join_intent
    index, prepared, plan = sample
    intent = _direct_intent(plan)
    change(intent)
    with pytest.raises(SelectionContractError):
        validate_schema_join_intent(intent, qualify_candidates(index, prepared))
