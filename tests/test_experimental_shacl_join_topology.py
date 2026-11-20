"""Offline tests for schema-derived shared-ancestor topology (Phase 4.4)."""
import copy

import pytest

from process_sim.dtwise.experimental_shacl_join_topology import verified_shared_ancestor
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


def test_deep_non_ecad_shared_ancestor():
    qualified = fixture_paths()
    found = verified_shared_ancestor(qualified, ["P1", "P2"], ancestor_uri="urn:unit")
    assert found["ancestor_uri"] == "urn:unit"
    assert len(found["shared_edges"]) == 2
    assert found["branch_ids"] == ["P1", "P2"]


def test_wrong_requested_ancestor_rejected():
    with pytest.raises(SelectionContractError, match="ancestor"):
        verified_shared_ancestor(fixture_paths(), ["P1", "P2"], ancestor_uri="urn:plant")


def test_duplicate_id_rejected():
    with pytest.raises(SelectionContractError, match="distinct"):
        verified_shared_ancestor(fixture_paths(), ["P1", "P1"])


def test_unknown_id_rejected():
    with pytest.raises(SelectionContractError, match="verified"):
        verified_shared_ancestor(fixture_paths(), ["P1", "P999"])


def test_disconnected_edge_rejected():
    qualified = fixture_paths()
    qualified["registry"]["P2"]["edges"][-1]["from"] = "urn:wrong"
    with pytest.raises(SelectionContractError, match="Disconnected"):
        verified_shared_ancestor(qualified, ["P1", "P2"])


def test_different_shared_edge_rejected():
    qualified = fixture_paths()
    qualified["registry"]["P2"]["edges"][1]["predicate"] = "https://example.org/alternate"
    found = verified_shared_ancestor(qualified, ["P1", "P2"])
    assert found["ancestor_uri"] == "urn:plant"


def test_non_sibling_ancestor_path_rejected():
    qualified = fixture_paths()
    p = qualified["registry"]["P2"]
    p["node_uris"] = p["node_uris"][:-1]
    p["edges"] = p["edges"][:-1]
    p["property"]["owner"] = "urn:unit"
    with pytest.raises(SelectionContractError, match="two branches"):
        verified_shared_ancestor(qualified, ["P1", "P2"])


def test_mismatched_domain_rejected():
    qualified = fixture_paths()
    qualified["registry"]["P2"]["domain"] = "ecad"
    with pytest.raises(SelectionContractError, match="domain"):
        verified_shared_ancestor(qualified, ["P1", "P2"])
