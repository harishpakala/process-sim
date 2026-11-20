"""Negative topology tests for the independent N-domain selection gate."""
import copy

import pytest

from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    prepare_n_domain_selection, validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def qualified(domain, owners):
    candidates, registry = [], {}
    for i, (owner, predicate) in enumerate(owners, 1):
        rid, pid = f"R{i}", f"P{i}"
        candidates.extend([
            {"id": rid, "domain": domain, "kind": "result", "path": owner},
            {"id": pid, "domain": domain, "kind": "property",
             "path": f"{owner} → Identifier"},
        ])
        registry[rid] = {"domain": domain, "kind": "result",
                         "node_uris": [owner], "edges": [],
                         "target_shape_uri": owner}
        registry[pid] = {"domain": domain, "kind": "property",
                         "node_uris": [owner], "edges": [],
                         "property": {"owner": owner, "predicate": predicate},
                         "owner_shape_uri": owner, "property_predicate_uri": predicate}
    return {"prompt": {"domain": domain, "candidates": candidates},
            "registry": registry}


def fixture():
    domains = {
        "a": qualified("a", [("a:Equipment", "urn:a:asset"),
                             ("a:Function", "urn:a:asset")]),
        "b": qualified("b", [("b:Device", "urn:b:asset")]),
    }
    mappings = {"ab": {"id": "ab", "left_domain": "a", "right_domain": "b",
                       "left_property": "urn:a:asset",
                       "right_property": "urn:b:asset", "verified": True}}
    prepared = prepare_n_domain_selection("Find equipment and device", domains, mappings)
    selection = {"status": "selected", "result_ids": ["a:R1", "b:R1"],
                 "identifier_path_ids": ["a:P1", "b:P1"],
                 "mapping_ids": ["ab"], "reason": "Selected owner paths"}
    return prepared, selection


def test_accepts_matching_result_and_identifier_owners():
    prepared, selection = fixture()
    assert validate_n_domain_selection(selection, prepared) == selection


def test_rejects_same_predicate_wrong_owner():
    prepared, selection = fixture()
    selection["identifier_path_ids"] = ["a:P2", "b:P1"]
    with pytest.raises(SelectionContractError, match="disconnected from identifier"):
        validate_n_domain_selection(selection, prepared)


def test_rejects_result_registry_owner_tampering():
    prepared, selection = fixture()
    prepared["result_registry"]["a:R1"]["target_shape_uri"] = "a:Function"
    with pytest.raises(SelectionContractError, match="Result owner mismatch"):
        validate_n_domain_selection(selection, prepared)


def test_rejects_identifier_registry_predicate_tampering():
    prepared, selection = fixture()
    prepared["result_registry"]["a:P1"]["property_predicate_uri"] = "urn:other"
    with pytest.raises(SelectionContractError, match="Identifier owner/predicate mismatch"):
        validate_n_domain_selection(selection, prepared)


def test_rejects_disconnected_owners_on_same_domain():
    prepared, selection = fixture()
    selection["identifier_path_ids"] = ["a:P1", "a:P2", "b:P1"]
    with pytest.raises(SelectionContractError, match="Disconnected identifier owners"):
        validate_n_domain_selection(selection, prepared)


def test_rejects_unverified_identifier_transition():
    prepared, selection = fixture()
    # One owner, two different identifier types; both mappings are approved,
    # but switching between their values is not automatically justified.
    domains = {
        "a": qualified("a", [("a:Equipment", "urn:a:asset")]),
        "b": qualified("b", [("b:Device", "urn:b:asset"),
                             ("b:Device", "urn:b:product")]),
        "c": qualified("c", [("c:Part", "urn:c:product")]),
    }
    mappings = {
        "ab": {"id": "ab", "left_domain": "a", "right_domain": "b",
               "left_property": "urn:a:asset", "right_property": "urn:b:asset",
               "verified": True},
        "bc": {"id": "bc", "left_domain": "b", "right_domain": "c",
               "left_property": "urn:b:product", "right_property": "urn:c:product",
               "verified": True},
    }
    prepared = prepare_n_domain_selection("Find equipment and part", domains, mappings)
    selection = {"status": "selected", "result_ids": ["a:R1", "c:R1"],
                 "identifier_path_ids": ["a:P1", "b:P1", "b:P2", "c:P1"],
                 "mapping_ids": ["ab", "bc"], "reason": "Two different keys"}
    with pytest.raises(SelectionContractError, match="identifier type transition"):
        validate_n_domain_selection(selection, prepared)


def test_rejects_malformed_selected_edge_sequence():
    prepared, selection = fixture()
    prepared["result_registry"]["a:R1"]["edges"] = [{"from": "x", "to": "y"}]
    with pytest.raises(SelectionContractError, match="Malformed selected SHACL"):
        validate_n_domain_selection(selection, prepared)
