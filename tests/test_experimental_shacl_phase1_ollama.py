"""Mocked-Ollama tests for opt-in Phase 1 intent and qualified paths."""
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


def mocked(response, *, assert_prompt=None):
    def transport(url, payload, timeout):
        assert url.endswith("/api/chat")
        assert payload["options"]["temperature"] == 0
        assert "Allowed operations: RETRIEVE, COUNT, EXISTS" in payload["messages"][0]["content"]
        prompt = json.loads(payload["messages"][1]["content"])
        assert prompt["domain"] == "ecad"
        assert prompt["allowed_operations"] == ["RETRIEVE", "COUNT", "EXISTS"]
        assert all(c["domain"] == "ecad" for c in prompt["candidates"])
        if assert_prompt:
            assert_prompt(prompt)
        return {"message": {"content": json.dumps(response)}}
    return transport


def reply(status="selected", operation="RETRIEVE", cid="P1", kind="property", idx=1):
    return {"status": status, "selected_candidate_ids": [cid],
            "operation": operation,
            "target": {"candidate_id": cid, "node_index": idx, "kind": kind},
            "modifiers": [], "reason": "Verified selection"}


def test_retrieve_qualified_property(setup):
    index, prepared = setup
    def check(prompt):
        assert any(c["kind"] == "property" and
                   c["path"] == "ECAD → Device → LocalId"
                   for c in prompt["candidates"])
    result = run_phase1_query_plan(index, prepared,
                                   transport=mocked(reply(), assert_prompt=check))
    assert result["plan"]["operation"] == "RETRIEVE"
    assert result["selected_paths"][0]["path"] == "ECAD → Device → LocalId"
    assert result["qualified"]["registry"]["P1"]["property_predicate_uri"] == "urn:localId"


@pytest.mark.parametrize("operation", ["COUNT", "EXISTS"])
def test_node_intents(setup, operation):
    index, prepared = setup
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(reply(operation=operation, cid="R2", kind="node")))
    assert result["plan"]["operation"] == operation
    assert result["selected_paths"][0]["path"] == "ECAD → Device"


@pytest.mark.parametrize("response", [
    reply(operation="SUM"),
    reply(cid="P999"),
    reply(operation="COUNT", cid="P1", kind="node"),
    reply(operation="RETRIEVE", cid="R2", kind="property"),
    reply(idx=0),
    {**reply(), "modifiers": [{"type": "FILTER_EQUALS"}]},
    {**reply(), "sparql": "DELETE WHERE { ?s ?p ?o }"},
])
def test_invalid_qwen_plan_fails_closed(setup, response):
    index, prepared = setup
    with pytest.raises(SelectionContractError):
        run_phase1_query_plan(index, prepared, transport=mocked(response))


def test_unsupported_filter_request_remains_unresolved(setup):
    index, prepared = setup
    prepared["prompt"]["question"] = 'Find Device where LocalId = "FI_101"'
    response = {"status": "unresolved", "selected_candidate_ids": [],
                "operation": None, "target": None, "modifiers": [],
                "reason": "FILTER_EQUALS is not supported in Phase 1"}
    result = run_phase1_query_plan(index, prepared, transport=mocked(response))
    assert result["plan"]["status"] == "unresolved"
    assert result["selected_paths"] == []


def test_no_candidates_skips_ollama(setup):
    index, prepared = setup
    prepared["prompt"]["candidates"] = []
    prepared["registry"] = {}
    result = run_phase1_query_plan(
        index, prepared, transport=lambda *_: pytest.fail("Must not call Qwen"))
    assert result["plan"]["status"] == "unresolved"


def test_domain_mismatch_before_ollama(setup):
    index, prepared = setup
    prepared["prompt"]["domain"] = "dexpi"
    with pytest.raises(ValueError, match="different domain"):
        run_phase1_query_plan(index, prepared,
                              transport=lambda *_: pytest.fail("Must not call Qwen"))
