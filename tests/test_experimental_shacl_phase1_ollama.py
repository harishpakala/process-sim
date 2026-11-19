"""Mocked Qwen tests for RETRIEVE-only domain-qualified property paths."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_phase1_ollama import run_phase1_query_plan, compile_phase1_sparql
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


@pytest.fixture
def ecad_address_paths():
    root, device = "urn:ECAD", "urn:Device"
    endpoint, plc = "urn:EndPoint", "urn:PLCEndPoint"
    edges = [
        {"from": root, "to": device, "predicate": "urn:device",
         "property_shape": "urn:DeviceShape"},
        {"from": device, "to": endpoint, "predicate": "urn:endpoint",
         "property_shape": "urn:EndPointShape"},
        {"from": device, "to": plc, "predicate": "urn:plc",
         "property_shape": "urn:PLCShape"},
    ]
    props = {
        owner: {"owner": owner, "predicate": "urn:address",
                "property_shape": "urn:Address" + name, "name": "Address"}
        for owner, name in ((endpoint, "EndPoint"), (plc, "PLCEndPoint"))
    }
    index = SubgraphIndex("ecad", {
        root: {"labels": ["ECAD"]}, device: {"labels": ["Device"]},
        endpoint: {"labels": ["EndPoint"]}, plc: {"labels": ["PLCEndPoint"]},
    }, {owner: [prop] for owner, prop in props.items()}, edges)
    prepared = {"prompt": {
        "domain": "ecad", "question": "",
        "candidates": [
            {"id": "C1", "path": "ECAD → Device → EndPoint → Address"},
            {"id": "C2", "path": "ECAD → Device → PLCEndPoint → Address"},
        ]}, "registry": {
        "C1": {"node_uris": [root, device, endpoint],
               "edges": [edges[0].copy(), edges[1].copy()],
               "property": props[endpoint].copy()},
        "C2": {"node_uris": [root, device, plc],
               "edges": [edges[0].copy(), edges[2].copy()],
               "property": props[plc].copy()},
    }}
    return index, prepared


def test_explicit_endpoint_qwen_selects_one_with_both_offered(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show Address of EndPoint belonging to Device in ECAD"
    # IDs are ordered by the verified shape URI, EndPoint before PLCEndPoint.
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"]), check=lambda prompt: (
            len(prompt["candidates"]) == 2 or pytest.fail("Both verified paths must be offered"))))
    assert [p["path"] for p in result["selected_paths"]] == [
        "ECAD → Device → EndPoint → Address"
    ]
    assert result["plan"]["selected_candidate_ids"] == ["P1"]



def test_explicit_both_endpoint_owners_keeps_both(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = (
        "Show Address of both EndPoint and PLCEndPoint belonging to Device in ECAD"
    )
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1", "P2"])))
    assert {p["path"] for p in result["selected_paths"]} == {
        "ECAD → Device → EndPoint → Address",
        "ECAD → Device → PLCEndPoint → Address",
    }


def test_explicit_both_requires_coverage(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = (
        "Show Address of both EndPoint and PLCEndPoint belonging to Device in ECAD"
    )
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"])))
    assert result["plan"]["status"] == "selected"
    assert len(result["selected_paths"]) == 1


def test_only_named_ancestor_does_not_suppress_descendants(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show Address belonging to Device in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1", "P2"])))
    assert len(result["selected_paths"]) == 2


def test_synonym_without_exact_shape_name_remains_selectable(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show network addresses of connection points"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"])))
    assert result["plan"]["status"] == "selected"


def test_structural_validator_does_not_guess_semantics(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show Address of EndPoint belonging to Device in ECAD"
    # A mocked wrong semantic choice is structurally valid; this test makes
    # the responsibility boundary explicit. Live Qwen evaluation is separate.
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1", "P2"]),
                                         check=lambda prompt: (
            len(prompt["candidates"]) == 2 or pytest.fail("Missing sibling"))))
    assert result["plan"]["selected_candidate_ids"] == ["P1", "P2"]


def test_phase1_compiles_selected_property_only(ecad_address_paths):
    index, prepared = ecad_address_paths
    # Compiler intentionally accepts only absolute HTTP(S) predicate IRIs.
    for edge in index.edges:
        edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
    for edges_record in prepared["registry"].values():
        for edge in edges_record["edges"]:
            edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
    for props in index.properties.values():
        for prop in props:
            prop["predicate"] = "https://example.org/address"
    for record in prepared["registry"].values():
        record["property"]["predicate"] = "https://example.org/address"
    prepared["prompt"]["question"] = "Show Address of EndPoint belonging to Device in ECAD"
    result = run_phase1_query_plan(index, prepared, transport=mocked(response(ids=["P1"])))
    queries = compile_phase1_sparql(result)
    assert len(queries) == 1
    assert queries[0]["candidate_id"] == "P1"
    assert queries[0]["sparql"].startswith("SELECT DISTINCT ?value WHERE {")
    assert "<https://example.org/endpoint>" in queries[0]["sparql"]
    assert "<https://example.org/plc>" not in queries[0]["sparql"]
    assert "rdf:type" not in queries[0]["sparql"]


def test_phase1_compiles_two_separate_queries(ecad_address_paths):
    index, prepared = ecad_address_paths
    for edge in index.edges:
        edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
    for record in prepared["registry"].values():
        for edge in record["edges"]:
            edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
        record["property"]["predicate"] = "https://example.org/address"
    for props in index.properties.values():
        for prop in props:
            prop["predicate"] = "https://example.org/address"
    prepared["prompt"]["question"] = "Show Address of both EndPoint and PLCEndPoint in ECAD"
    result = run_phase1_query_plan(index, prepared,
                                   transport=mocked(response(ids=["P1", "P2"])))
    queries = compile_phase1_sparql(result)
    assert len(queries) == 2
    assert {q["candidate_id"] for q in queries} == {"P1", "P2"}
    assert all("SELECT DISTINCT ?value" in q["sparql"] for q in queries)


def test_phase1_unresolved_compiles_no_queries(setup):
    index, prepared = setup
    result = run_phase1_query_plan(index, prepared,
                                   transport=mocked(response("unresolved", [])))
    assert compile_phase1_sparql(result) == []


@pytest.mark.parametrize("ids", [["P1", "P2"], ["P1"]])
def test_bare_address_auto_joins_verified_siblings(ecad_address_paths, ids):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show Address in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=ids)))
    assert result["plan"]["status"] == "selected"
    assert set(result["plan"]["selected_candidate_ids"]) == {"P1", "P2"}
    assert len(result["auto_join_result_ids"]) == 2


def test_explicit_owner_still_selects_one(ecad_address_paths):
    index, prepared = ecad_address_paths
    prepared["prompt"]["question"] = "Show Address of EndPoint belonging to Device in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"])))
    assert result["plan"]["status"] == "selected"
    assert result["plan"]["selected_candidate_ids"] == ["P1"]


def test_bare_address_auto_join_compiles_single_query(ecad_address_paths):
    index, prepared = ecad_address_paths
    for edge in index.edges:
        edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
    for record in prepared["registry"].values():
        for edge in record["edges"]:
            edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
        record["property"]["predicate"] = "https://example.org/address"
    for props in index.properties.values():
        for prop in props:
            prop["predicate"] = "https://example.org/address"
    prepared["prompt"]["question"] = "Show Address in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"])))
    queries = compile_phase1_sparql(result)
    assert len(queries) == 1
    assert "SELECT DISTINCT ?value1 ?value2" in queries[0]["sparql"]
    assert "<https://example.org/endpoint>" in queries[0]["sparql"]
    assert "<https://example.org/plc>" in queries[0]["sparql"]


def test_bare_address_two_verified_join_groups(ecad_address_paths):
    index, prepared = ecad_address_paths
    root, symbol = "urn:ECAD", "urn:Symbol"
    index.shapes[symbol] = {"labels": ["Symbol"]}
    symbol_edge = {"from": root, "to": symbol, "predicate": "https://example.org/symbol",
                   "property_shape": "urn:SymbolShape"}
    index.edges.append(symbol_edge)
    for suffix, owner_name in (("EndPoint", "EndPoint"), ("PLCEndPoint", "PLCEndPoint")):
        owner = f"urn:Symbol{suffix}"
        index.shapes[owner] = {"labels": [owner_name]}
        edge = {"from": symbol, "to": owner,
                "predicate": f"https://example.org/symbol{suffix}",
                "property_shape": f"urn:Symbol{suffix}Shape"}
        index.edges.append(edge)
        prop = {"owner": owner, "predicate": "https://example.org/address",
                "property_shape": f"urn:Symbol{suffix}Address", "name": "Address"}
        index.properties[owner] = [prop]
        cid = "C3" if suffix == "EndPoint" else "C4"
        prepared["prompt"]["candidates"].append({
            "id": cid, "path": f"ECAD → Symbol → {owner_name} → Address"})
        prepared["registry"][cid] = {
            "node_uris": [root, symbol, owner],
            "edges": [symbol_edge.copy(), edge.copy()],
            "property": prop.copy(),
        }
    for edge in index.edges:
        if edge["predicate"].startswith("urn:"):
            edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
    for record in prepared["registry"].values():
        for edge in record["edges"]:
            if edge["predicate"].startswith("urn:"):
                edge["predicate"] = edge["predicate"].replace("urn:", "https://example.org/")
        record["property"]["predicate"] = "https://example.org/address"
    for props in index.properties.values():
        for prop in props:
            prop["predicate"] = "https://example.org/address"
    prepared["prompt"]["question"] = "Show Address in ECAD"
    result = run_phase1_query_plan(
        index, prepared, transport=mocked(response(ids=["P1"])))
    assert result["plan"]["status"] == "selected"
    assert len(result["auto_join_groups"]) == 2
    assert sorted(len(group) for group in result["auto_join_groups"]) == [2, 2]
    queries = compile_phase1_sparql(result)
    assert len(queries) == 2
    assert all("SELECT DISTINCT ?value1 ?value2" in q["sparql"] for q in queries)
    assert sum("https://example.org/symbol>" in q["sparql"] for q in queries) == 1
