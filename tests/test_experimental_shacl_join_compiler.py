"""Phase 4.5 offline tests for generic sibling-join compilation."""
import copy

import pytest

from process_sim.dtwise.experimental_shacl_join_compiler import compile_verified_sibling_join
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
def fixture_paths():
    root, plant, unit, left, right = ("urn:root", "urn:plant", "urn:unit",
                                      "urn:left", "urn:right")
    def edge(a, b):
        return {"from": a, "to": b, "predicate": "https://example.org/" + b[4:],
                "property_shape": "urn:link:" + b}
    common = [edge(root, plant), edge(plant, unit)]
    def record(owner, branch):
        return {"domain": "other", "kind": "property",
                "node_uris": [root, plant, unit, owner],
                "edges": copy.deepcopy(common) + [branch],
                "property": {"owner": owner, "predicate": "https://example.org/value"}}
    return {"prompt": {"domain": "other", "candidates": [
        {"id": "P1", "kind": "property"}, {"id": "P2", "kind": "property"}]},
        "registry": {"P1": record(left, edge(unit, left)),
                     "P2": record(right, edge(unit, right))}}



def test_deep_non_ecad_compiles_shared_prefix_once():
    query = compile_verified_sibling_join(fixture_paths(), ["P1", "P2"])
    assert query.startswith("SELECT DISTINCT ?value1 ?value2 WHERE {")
    assert query.count("?n0 <https://example.org/plant> ?n1 .") == 1
    assert query.count("?n1 <https://example.org/unit> ?n2 .") == 1
    assert "?n2 <https://example.org/left> ?b1_3 ." in query
    assert "?n2 <https://example.org/right> ?b2_3 ." in query
    assert "?b1_3 <https://example.org/value> ?value1 ." in query
    assert "?b2_3 <https://example.org/value> ?value2 ." in query


def test_result_order_controls_projection_order():
    query = compile_verified_sibling_join(fixture_paths(), ["P2", "P1"])
    assert "?n2 <https://example.org/right> ?b1_3 ." in query
    assert "?n2 <https://example.org/left> ?b2_3 ." in query


def test_one_level_shared_root():
    q = fixture_paths()
    for item in q["registry"].values():
        item["node_uris"] = [item["node_uris"][0], item["node_uris"][-1]]
        item["edges"] = [dict(item["edges"][-1], **{"from": "urn:root"})]
    query = compile_verified_sibling_join(q, ["P1", "P2"])
    assert "?n0 <https://example.org/left> ?b1_1 ." in query
    assert "?n0 <https://example.org/right> ?b2_1 ." in query


def test_different_shared_predicate_keeps_branches_separate():
    q = fixture_paths()
    q["registry"]["P2"]["edges"][1]["predicate"] = "https://example.org/alternate"
    query = compile_verified_sibling_join(q, ["P1", "P2"])
    assert "?n1 <https://example.org/unit> ?b1_2 ." in query
    assert "?n1 <https://example.org/alternate> ?b2_2 ." in query


@pytest.mark.parametrize("ids", [["P1", "P1"], ["P1", "P404"]])
def test_invalid_ids_rejected(ids):
    with pytest.raises(SelectionContractError):
        compile_verified_sibling_join(fixture_paths(), ids)


def test_invalid_path_rejected():
    q = fixture_paths()
    q["registry"]["P1"]["property"]["owner"] = "urn:wrong"
    with pytest.raises(SelectionContractError, match="owner"):
        compile_verified_sibling_join(q, ["P1", "P2"])


def test_ecad_shape_compiles_without_hardcoded_predicates():
    root, device, endpoint, plc = ("urn:ecad", "urn:device", "urn:endpoint", "urn:plc")
    def edge(a, b, predicate):
        return {"from": a, "to": b, "predicate": predicate, "property_shape": "urn:edge:" + b}
    shared = edge(root, device, "https://example.org/ecad/hasDevice")
    def path(owner, branch_pred):
        return {"domain": "ecad", "kind": "property",
                "node_uris": [root, device, owner],
                "edges": [copy.deepcopy(shared), edge(device, owner, branch_pred)],
                "property": {"owner": owner, "predicate": "https://example.org/ecad/hasAddress"}}
    q = {"prompt": {"domain": "ecad", "candidates": [
        {"id": "P1", "kind": "property"}, {"id": "P2", "kind": "property"}]},
        "registry": {
            "P1": path(endpoint, "https://example.org/ecad/hasEndPoint"),
            "P2": path(plc, "https://example.org/ecad/hasPLCEndPoint")}}
    query = compile_verified_sibling_join(q, ["P1", "P2"])
    assert query.count("<https://example.org/ecad/hasDevice>") == 1
    assert "<https://example.org/ecad/hasEndPoint>" in query
    assert "<https://example.org/ecad/hasPLCEndPoint>" in query
    assert query.count("<https://example.org/ecad/hasAddress>") == 2
