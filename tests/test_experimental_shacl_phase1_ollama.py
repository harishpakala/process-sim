"""Mocked Qwen tests for RETRIEVE-only domain-qualified property paths."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_phase1_ollama import run_phase1_query_plan
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


@pytest.fixture
def setup():
    root, device = "urn:ECAD", "urn:Device"
    edge = {"from": root, "to": device, "predicate": "urn:device",
            "property_shape": "urn:DevicePropertyShape"}
    prop = {"owner": device, "predicate": "urn:localId",
            "property_shape": "urn:LocalIdPropertyShape", "name": "LocalId"}
    index = SubgraphIndex("ecad", {
        root: {"labels": ["ECAD"]}, device: {"labels": ["Device"]},
    }, {device: [prop]}, [edge])
    prepared = {
        "prompt": {"domain": "ecad", "question": "Show LocalId of Device in ECAD",
                   "candidates": [{"id": "C1", "path": "ECAD → Device → LocalId"}]},
        "registry": {"C1": {"node_uris": [root, device], "edges": [edge.copy()],
                             "property": prop.copy()}},
    }
    return index, prepared


def response(status="selected", ids=None):
    return {"status": status,
            "selected_candidate_ids": ["P1"] if ids is None else ids,
            "reason": "Verified property path selection"}


def mocked(reply, check=None):
    def transport(url, payload, timeout):
        assert url.endswith("/api/chat")
        assert payload["options"]["temperature"] == 0
        assert "only supported task is RETRIEVE" in payload["messages"][0]["content"]
        prompt = json.loads(payload["messages"][1]["content"])
        assert prompt["domain"] == "ecad"
        assert all(c["kind"] == "property" and c["domain"] == "ecad"
                   for c in prompt["candidates"])
        if check:
            check(prompt)
        return {"message": {"content": json.dumps(reply)}}
    return transport


def test_retrieve_qualified_property(setup):
    index, prepared = setup
    result = run_phase1_query_plan(index, prepared, transport=mocked(response()))
    assert result["plan"]["operation"] == "RETRIEVE"
    assert result["selected_paths"][0]["path"] == "ECAD → Device → LocalId"
    assert result["qualified"]["registry"]["P1"]["property_predicate_uri"] == "urn:localId"


def test_multiple_explicit_property_paths(setup):
    index, prepared = setup
    device = "urn:Device"
    other = "urn:PLCEndPoint"
    index.shapes[other] = {"labels": ["PLCEndPoint"]}
    index.edges.append({"from": "urn:ECAD", "to": other, "predicate": "urn:plc",
                        "property_shape": "urn:PLCPropertyShape"})
    prop = {"owner": other, "predicate": "urn:localId",
            "property_shape": "urn:PLCLocalId", "name": "LocalId"}
    index.properties[other] = [prop]
    prepared["prompt"]["candidates"].append({"id": "C2", "path": "ECAD → PLCEndPoint → LocalId"})
    prepared["registry"]["C2"] = {
        "node_uris": ["urn:ECAD", other], "edges": [index.edges[-1].copy()],
        "property": prop.copy(),
    }
    prepared["prompt"]["question"] = "Show LocalId of both Device and PLCEndPoint in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1", "P2"])))
    assert len(result["selected_paths"]) == 2
    assert {p["path"] for p in result["selected_paths"]} == {
        "ECAD → Device → LocalId", "ECAD → PLCEndPoint → LocalId",
    }


@pytest.mark.parametrize("bad", [
    response(ids=["P999"]),
    response(ids=["R1"]),
    response(ids=["P1", "P1"]),
    {**response(), "operation": "COUNT"},
    {**response(), "sparql": "DELETE WHERE { ?s ?p ?o }"},
])
def test_invalid_qwen_output_fails_closed(setup, bad):
    index, prepared = setup
    with pytest.raises(SelectionContractError):
        run_phase1_query_plan(index, prepared, transport=mocked(bad))


@pytest.mark.parametrize("status", ["ambiguous", "unresolved"])
def test_uncertain_status_has_no_paths(setup, status):
    index, prepared = setup
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(status, ids=[])))
    assert result["plan"]["status"] == status
    assert result["selected_paths"] == []


@pytest.mark.parametrize("question", [
    'Find Device where LocalId = "FI_101"',
    "How many Device instances in ECAD?",
    "Does any Device exist in ECAD?",
])
def test_explicit_unsupported_request_skips_qwen(setup, question):
    index, prepared = setup
    prepared["prompt"]["question"] = question
    result = run_phase1_query_plan(
        index, prepared, transport=lambda *_: pytest.fail("Must not call Qwen"))
    assert result["plan"]["status"] == "unresolved"


def test_no_candidates_skips_qwen(setup):
    index, prepared = setup
    prepared["prompt"]["candidates"] = []
    prepared["registry"] = {}
    result = run_phase1_query_plan(
        index, prepared, transport=lambda *_: pytest.fail("Must not call Qwen"))
    assert result["plan"]["status"] == "unresolved"


def test_domain_mismatch_before_qwen(setup):
    index, prepared = setup
    prepared["prompt"]["domain"] = "dexpi"
    with pytest.raises(ValueError, match="different domain"):
        run_phase1_query_plan(index, prepared,
                              transport=lambda *_: pytest.fail("Must not call Qwen"))
