"""Offline Phase 2 equality-filter tests; no Ollama service required."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_phase2_filter import (
    run_phase2_filter_plan, compile_phase2_filter_sparql,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


@pytest.fixture
def sample():
    root, device, endpoint = "urn:ECAD", "urn:Device", "urn:EndPoint"
    edges = [
        {"from": root, "to": device, "predicate": "https://example.org/hasDevice",
         "property_shape": "urn:DeviceLink"},
        {"from": device, "to": endpoint, "predicate": "https://example.org/hasEndPoint",
         "property_shape": "urn:EndpointLink"},
    ]
    local = {"owner": device, "predicate": "https://example.org/localId",
             "property_shape": "urn:LocalId", "name": "LocalId"}
    address = {"owner": endpoint, "predicate": "https://example.org/address",
               "property_shape": "urn:Address", "name": "Address"}
    index = SubgraphIndex("ecad", {
        root: {"labels": ["ECAD"]}, device: {"labels": ["Device"]},
        endpoint: {"labels": ["EndPoint"]},
    }, {device: [local], endpoint: [address]}, edges)
    prepared = {"prompt": {"domain": "ecad",
                           "question": 'Show Address of EndPoint where Device LocalId = "FI_101" in ECAD',
                           "candidates": [
                               {"id": "C1", "path": "ECAD → Device → LocalId"},
                               {"id": "C2", "path": "ECAD → Device → EndPoint → Address"},
                           ]},
                "registry": {
                    "C1": {"node_uris": [root, device], "edges": [edges[0]],
                           "property": local},
                    "C2": {"node_uris": [root, device, endpoint], "edges": edges,
                           "property": address},
                }}
    return index, prepared


def transport(plan):
    def reply(url, payload, timeout):
        assert payload["messages"][0]["content"].startswith("Plan a single-domain")
        return {"message": {"content": json.dumps(plan)}}
    return reply


def selected(result_id="P1", filter_id="P2", value="FI_101"):
    return {"status": "selected", "result_id": result_id, "filter_id": filter_id,
            "operator": "=", "value": value, "reason": "Matches owner and filter"}


def test_one_filter_uses_shared_device_variable(sample):
    index, prepared = sample
    # P IDs sorted by node URI: EndPoint Address before Device LocalId?
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    qualified = qualify_candidates(index, prepared)
    ids = {c["property_name"]: c["id"] for c in qualified["prompt"]["candidates"]
           if c["kind"] == "property"}
    plan = selected(ids["Address"], ids["LocalId"])
    result = run_phase2_filter_plan(index, prepared, transport=transport(plan))
    queries = compile_phase2_filter_sparql(result)
    assert len(queries) == 1
    query = queries[0]["sparql"]
    assert "SELECT DISTINCT ?value WHERE {" in query
    assert "?n1 <https://example.org/localId> ?filterValue ." in query
    assert "?n2 <https://example.org/address> ?value ." in query
    assert 'FILTER(?filterValue = "FI_101")' in query


def test_wrong_literal_rejected(sample):
    index, prepared = sample
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    q = qualify_candidates(index, prepared)
    ids = {c["property_name"]: c["id"] for c in q["prompt"]["candidates"]
           if c["kind"] == "property"}
    with pytest.raises(SelectionContractError, match="value"):
        run_phase2_filter_plan(index, prepared,
                               transport=transport(selected(ids["Address"], ids["LocalId"], "invented")))


def test_missing_filter_skips_model(sample):
    index, prepared = sample
    prepared["prompt"]["question"] = "Show Address of EndPoint"
    result = run_phase2_filter_plan(index, prepared,
                                    transport=lambda *_: pytest.fail("Must not call model"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase2_filter_sparql(result) == []


def test_filter_on_descendant_rejected(sample):
    index, prepared = sample
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    q = qualify_candidates(index, prepared)
    ids = {c["property_name"]: c["id"] for c in q["prompt"]["candidates"]
           if c["kind"] == "property"}
    with pytest.raises(SelectionContractError, match="Filter owner"):
        run_phase2_filter_plan(index, prepared,
                               transport=transport(selected(ids["LocalId"], ids["Address"])))


def test_powershell_unquoted_identifier(sample):
    index, prepared = sample
    prepared["prompt"]["question"] = (
        "Show Address of EndPoint belonging to Device where Device LocalId = FI_101 in ECAD"
    )
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    q = qualify_candidates(index, prepared)
    ids = {c["property_name"]: c["id"] for c in q["prompt"]["candidates"]
           if c["kind"] == "property"}
    result = run_phase2_filter_plan(index, prepared,
                                    transport=transport(selected(ids["Address"], ids["LocalId"])))
    assert result["plan"]["status"] == "selected"
    assert 'FILTER(?filterValue = "FI_101")' in compile_phase2_filter_sparql(result)[0]["sparql"]


def test_two_result_paths_share_one_device_filter(sample):
    index, prepared = sample
    root, device = "urn:ECAD", "urn:Device"
    plc = "urn:PLCEndPoint"
    edge = {"from": device, "to": plc, "predicate": "https://example.org/hasPLCEndPoint",
            "property_shape": "urn:PLCLink"}
    address = {"owner": plc, "predicate": "https://example.org/address",
               "property_shape": "urn:PLCAddress", "name": "Address"}
    index.shapes[plc] = {"labels": ["PLCEndPoint"]}
    index.properties[plc] = [address]
    # Avoid mutating the fixture edges list also referenced by C2.\n    index.edges = [*index.edges, edge]
    prepared["prompt"]["question"] = (
        "Show Address of both EndPoint and PLCEndPoint belonging to Device "
        "where Device LocalId = FI_101 in ECAD"
    )
    prepared["prompt"]["candidates"].append(
        {"id": "C3", "path": "ECAD → Device → PLCEndPoint → Address"})
    prepared["registry"]["C3"] = {
        "node_uris": [root, device, plc],
        "edges": [index.edges[0], edge], "property": address,
    }
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    qualified = qualify_candidates(index, prepared)
    ids = {c["path"]: c["id"] for c in qualified["prompt"]["candidates"]
           if c["kind"] == "property"}
    device_id = next(c["id"] for c in qualified["prompt"]["candidates"]
                     if c["kind"] == "property" and c["property_name"] == "LocalId")
    result_ids = [ids["ECAD → Device → EndPoint → Address"],
                  ids["ECAD → Device → PLCEndPoint → Address"]]
    plan = {"status": "selected", "result_ids": result_ids,
            "filter_id": device_id, "operator": "=", "value": "FI_101",
            "reason": "Both requested endpoint owners with shared Device filter"}
    result = run_phase2_filter_plan(index, prepared, transport=transport(plan))
    queries = compile_phase2_filter_sparql(result)
    assert len(queries) == 2
    assert {q["result_id"] for q in queries} == set(result_ids)
    assert all("?n1 <https://example.org/localId> ?filterValue ." in q["sparql"]
               for q in queries)
    assert all('FILTER(?filterValue = "FI_101")' in q["sparql"] for q in queries)
    assert any("<https://example.org/hasEndPoint>" in q["sparql"] for q in queries)
    assert any("<https://example.org/hasPLCEndPoint>" in q["sparql"] for q in queries)


def test_duplicate_result_ids_rejected(sample):
    index, prepared = sample
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    q = qualify_candidates(index, prepared)
    ids = {c["property_name"]: c["id"] for c in q["prompt"]["candidates"]
           if c["kind"] == "property"}
    plan = {"status": "selected", "result_ids": [ids["Address"], ids["Address"]],
            "filter_id": ids["LocalId"], "operator": "=", "value": "FI_101",
            "reason": "duplicate"}
    with pytest.raises(SelectionContractError, match="Unknown or non-property"):
        run_phase2_filter_plan(index, prepared, transport=transport(plan))
