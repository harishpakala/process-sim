"""Offline tests for domain-qualified SHACL candidate adapter."""
import copy

import pytest

from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


def fixture(domain="ecad"):
    root, owner = f"urn:{domain}:Root", f"urn:{domain}:Device"
    edge = {"from": root, "to": owner, "predicate": "urn:hasDevice",
            "property_shape": "urn:hasDeviceShape"}
    prop = {"owner": owner, "predicate": "urn:localId",
            "property_shape": "urn:LocalIdShape", "name": "LocalId"}
    index = SubgraphIndex(
        domain, {root: {"labels": ["ECAD"]}, owner: {"labels": ["Device"]}},
        {owner: [prop]}, [edge],
    )
    prepared = {
        "prompt": {"domain": domain, "question": "Show Device LocalId",
                   "candidates": [{"id": "C1", "path": "ECAD → Device → LocalId"}]},
        "registry": {"C1": {"node_uris": [root, owner], "edges": [copy.deepcopy(edge)],
                             "property": copy.deepcopy(prop)}},
    }
    return index, prepared


def test_domain_and_full_property_path():
    index, prepared = fixture()
    qualified = qualify_candidates(index, prepared)
    assert qualified["prompt"]["domain"] == "ecad"
    properties = [c for c in qualified["prompt"]["candidates"]
                  if c["kind"] == "property"]
    assert len(properties) == 1
    assert properties[0]["path"] == "ECAD → Device → LocalId"
    record = qualified["registry"][properties[0]["id"]]
    assert record["domain"] == "ecad"
    assert record["owner_shape_uri"] == "urn:ecad:Device"
    assert record["property_predicate_uri"] == "urn:localId"


def test_result_prefixes_are_distinct_and_verified():
    index, prepared = fixture()
    qualified = qualify_candidates(index, prepared)
    results = [c for c in qualified["prompt"]["candidates"] if c["kind"] == "result"]
    assert {c["path"] for c in results} == {"ECAD", "ECAD → Device"}
    assert all(qualified["registry"][c["id"]]["property"] is None for c in results)


def test_same_property_name_in_other_domain_is_not_accepted():
    index, prepared = fixture("ecad")
    other, _ = fixture("dexpi")
    with pytest.raises(ValueError, match="different domain"):
        qualify_candidates(other, prepared)
    prepared["registry"]["C1"]["property"]["owner"] = "urn:dexpi:Device"
    with pytest.raises(ValueError, match="not verified"):
        qualify_candidates(index, prepared)


def test_reject_invented_edge():
    index, prepared = fixture()
    prepared["registry"]["C1"]["edges"][0]["predicate"] = "urn:invented"
    with pytest.raises(ValueError, match="not verified"):
        qualify_candidates(index, prepared)


def test_reject_duplicate_or_missing_registry_ids():
    index, prepared = fixture()
    prepared["prompt"]["candidates"].append({"id": "C1", "path": "duplicate"})
    with pytest.raises(ValueError, match="disagree"):
        qualify_candidates(index, prepared)


def test_shared_prefix_is_deduplicated():
    index, prepared = fixture()
    second = {"owner": "urn:ecad:Device", "predicate": "urn:serial",
              "property_shape": "urn:SerialShape", "name": "Serial"}
    index.properties["urn:ecad:Device"].append(second)
    prepared["prompt"]["candidates"].append(
        {"id": "C2", "path": "ECAD → Device → Serial"})
    prepared["registry"]["C2"] = {
        "node_uris": prepared["registry"]["C1"]["node_uris"][:],
        "edges": prepared["registry"]["C1"]["edges"][:],
        "property": second,
    }
    qualified = qualify_candidates(index, prepared)
    assert len([c for c in qualified["prompt"]["candidates"] if c["kind"] == "result"]) == 2
    assert len([c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"]) == 2


def test_legacy_prepared_unchanged():
    index, prepared = fixture()
    before = copy.deepcopy(prepared)
    qualify_candidates(index, prepared)
    assert prepared == before
