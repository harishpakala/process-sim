"""Cross-domain mapping qualification must never infer an unapproved join."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import (
    load_cross_domain_mappings, qualify_cross_domain_mappings,
    validate_cross_domain_mapping_selection,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def mapping(**changes):
    result = {
        "id": "dexpi-ecad-asset-identifier",
        "left_domain": "dexpi", "right_domain": "ecad",
        "left_property": "urn:dexpi:hasAssetIdentifier",
        "right_property": "urn:ecad:hasAssetIdentifier",
        "evidence_ids": ["urn:shacl:evidence"],
        "verified": True,
    }
    result.update(changes)
    return result


def load(tmp_path, records):
    path = tmp_path / "cross-domain-mappings.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return load_cross_domain_mappings(path)


def test_approved_mapping_is_offered_and_validated(tmp_path):
    registry = load(tmp_path, [mapping()])
    offered = qualify_cross_domain_mappings(registry, {
        "dexpi": {"urn:dexpi:hasAssetIdentifier"},
        "ecad": {"urn:ecad:hasAssetIdentifier"},
    })
    assert [item["id"] for item in offered] == ["dexpi-ecad-asset-identifier"]
    assert validate_cross_domain_mapping_selection(offered[0]["id"], offered, registry) == mapping()


def test_missing_shacl_property_does_not_qualify(tmp_path):
    registry = load(tmp_path, [mapping()])
    assert qualify_cross_domain_mappings(registry, {
        "dexpi": {"urn:dexpi:hasAssetIdentifier"}, "ecad": set(),
    }) == []


def test_unverified_mapping_does_not_qualify(tmp_path):
    registry = load(tmp_path, [mapping(verified=False)])
    assert qualify_cross_domain_mappings(registry, {
        "dexpi": {"urn:dexpi:hasAssetIdentifier"},
        "ecad": {"urn:ecad:hasAssetIdentifier"},
    }) == []


def test_model_cannot_invent_mapping_id(tmp_path):
    registry = load(tmp_path, [mapping()])
    with pytest.raises(SelectionContractError, match="not offered"):
        validate_cross_domain_mapping_selection("made-up", [], registry)


@pytest.mark.parametrize("records", [
    [mapping(), mapping()],
    [mapping(evidence_ids=[])],
    [mapping(right_domain="dexpi")],
    [{"id": "incomplete"}],
])
def test_invalid_mapping_file_fails_closed(tmp_path, records):
    with pytest.raises(SelectionContractError):
        load(tmp_path, records)


def test_tampered_offered_mapping_is_rejected(tmp_path):
    registry = load(tmp_path, [mapping()])
    offered = [{
        "id": "dexpi-ecad-asset-identifier",
        "left_domain": "dexpi", "right_domain": "ecad",
        "left_property": "urn:dexpi:hasAssetIdentifier",
        "right_property": "urn:ecad:wrong",
    }]
    with pytest.raises(SelectionContractError, match="differs"):
        validate_cross_domain_mapping_selection(offered[0]["id"], offered, registry)


def test_empty_owner_approvals_are_preserved_not_inferred(tmp_path):
    record = mapping(approved_owner_pairs=[])
    assert load(tmp_path, [record])[record["id"]]["approved_owner_pairs"] == []


def test_evidenced_owner_pair_metadata_loads(tmp_path):
    pair = {
        "left_owner_shape_uri": "urn:dexpi:EquipmentShape",
        "right_owner_shape_uri": "urn:ecad:DeviceShape",
        "evidence_ids": ["urn:approval:owner-pair"],
    }
    record = mapping(approved_owner_pairs=[pair])
    assert load(tmp_path, [record])[record["id"]]["approved_owner_pairs"] == [pair]


@pytest.mark.parametrize("pairs", [
    None, "all", {}, [""], [{"left_owner_shape_uri": "urn:left"}],
    [{"left_owner_shape_uri": "urn:left", "right_owner_shape_uri": "urn:right",
      "evidence_ids": []}],
    [{"left_owner_shape_uri": "urn:left", "right_owner_shape_uri": "urn:right",
      "evidence_ids": ["urn:proof"]}] * 2,
])
def test_invalid_owner_pair_metadata_rejected(tmp_path, pairs):
    # Explicit null is invalid; absence of the optional field remains valid.
    with pytest.raises(SelectionContractError):
        load(tmp_path, [mapping(approved_owner_pairs=pairs)])
