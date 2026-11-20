"""Offline regression tests for opt-in Phase 4.1 sibling joins."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_join_compiler import compile_verified_sibling_join
from process_sim.dtwise.experimental_shacl_phase4_join import (
    compile_phase4_join_sparql, run_phase4_join_plan, validate_phase4_join_plan,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


@pytest.fixture
def sample():
    root, device, endpoint, plc = "urn:ECAD", "urn:Device", "urn:EndPoint", "urn:PLCEndPoint"
    e0 = {"from": root, "to": device, "predicate": "https://example.org/ecad/hasDevice",
          "property_shape": "urn:DeviceLink"}
    e1 = {"from": device, "to": endpoint,
          "predicate": "https://example.org/ecad/hasEndPoint", "property_shape": "urn:EndpointLink"}
    e2 = {"from": device, "to": plc,
          "predicate": "https://example.org/ecad/hasPLCEndPoint", "property_shape": "urn:PLCLink"}
    p1 = {"owner": endpoint, "predicate": "https://example.org/ecad/hasAddress",
          "property_shape": "urn:EndpointAddress", "name": "Address"}
    p2 = {"owner": plc, "predicate": "https://example.org/ecad/hasAddress",
          "property_shape": "urn:PLCAddress", "name": "Address"}
    index = SubgraphIndex("ecad", {root: {"labels": ["ECAD"]},
                                   device: {"labels": ["Device"]},
                                   endpoint: {"labels": ["EndPoint"]},
                                   plc: {"labels": ["PLCEndPoint"]}},
                          {endpoint: [p1], plc: [p2]}, [e0, e1, e2])
    question = ("Show EndPoint Address and PLCEndPoint Address belonging "
                "to the same Device in ECAD")
    prepared = {"prompt": {"domain": "ecad", "question": question,
                           "candidates": [{"id": "C1", "path": "endpoint"},
                                          {"id": "C2", "path": "plc"}]},
                "registry": {
                    "C1": {"node_uris": [root, device, endpoint], "edges": [e0, e1], "property": p1},
                    "C2": {"node_uris": [root, device, plc], "edges": [e0, e2], "property": p2},
                }}
    qualified = qualify_candidates(index, prepared)
    ids = [c["id"] for c in qualified["prompt"]["candidates"] if c["kind"] == "property"]
    plan = {"status": "selected", "result_ids": ids,
            "join_owner": "Device", "reason": "Both properties share Device"}
    return index, prepared, plan


def transport(plan):
    return lambda *_: {"message": {"content": json.dumps(plan)}}


def test_shared_device_compiles_single_join(sample):
    index, prepared, plan = sample
    result = run_phase4_join_plan(index, prepared, transport=transport(plan))
    query = compile_phase4_join_sparql(result)
    assert result["plan"]["status"] == "selected"
    assert query.count("hasDevice") == 1
    assert "SELECT DISTINCT ?endpointAddress ?plcAddress WHERE {" in query
    assert "?device <https://example.org/ecad/hasEndPoint> ?endpoint ." in query
    assert "?device <https://example.org/ecad/hasPLCEndPoint> ?plcEndpoint ." in query
    assert query.count("hasAddress") == 2


def test_missing_result_rejected(sample):
    index, prepared, plan = sample
    plan["result_ids"] = plan["result_ids"][:1]
    with pytest.raises(SelectionContractError, match="two distinct"):
        run_phase4_join_plan(index, prepared, transport=transport(plan))


def test_wrong_join_owner_rejected(sample):
    index, prepared, plan = sample
    plan["join_owner"] = "EndPoint"
    with pytest.raises(SelectionContractError, match="owner interpretation"):
        run_phase4_join_plan(index, prepared, transport=transport(plan))


def test_duplicate_result_rejected(sample):
    index, prepared, plan = sample
    plan["result_ids"][1] = plan["result_ids"][0]
    with pytest.raises(SelectionContractError, match="two distinct"):
        run_phase4_join_plan(index, prepared, transport=transport(plan))


def test_unrecognized_question_abstains_without_model(sample):
    index, prepared, plan = sample
    prepared["prompt"]["question"] = "Show all addresses in ECAD"
    result = run_phase4_join_plan(
        index, prepared, transport=lambda *_: pytest.fail("Model should not be called"))
    assert result["plan"]["status"] == "unresolved"
    assert compile_phase4_join_sparql(result) is None


def test_non_shared_device_edge_rejected(sample):
    index, prepared, plan = sample
    qualified = qualify_candidates(index, prepared)
    plc = qualified["registry"][plan["result_ids"][1]]
    plc["edges"][0] = dict(plc["edges"][0], predicate="urn:invented")
    with pytest.raises(SelectionContractError, match="shared Device"):
        validate_phase4_join_plan(plan, qualified)


def test_generic_compiler_preserves_phase41_graph_semantics(sample):
    """Compare the two compilers using the same selected, verified paths."""
    index, prepared, plan = sample
    result = run_phase4_join_plan(index, prepared, transport=transport(plan))
    legacy = compile_phase4_join_sparql(result)
    qualified = result["qualified"]
    # Phase 4.1 orders projections by explicit semantic paths, not model ID order.
    from process_sim.dtwise.experimental_shacl_phase4_join import _expected_paths
    generic = compile_verified_sibling_join(qualified, list(_expected_paths(qualified)))
    # The graph patterns should be identical modulo variable names.
    rename = {
        "?n0": "?ecad", "?n1": "?device",
        "?b1_2": "?endpoint", "?b2_2": "?plcEndpoint",
        "?value1": "?endpointAddress", "?value2": "?plcAddress",
    }
    for source, target in rename.items():
        generic = generic.replace(source, target)
    assert generic == legacy
