"""Owner-specific mapping graph qualification and selection tests."""
import pytest

from process_sim.dtwise.experimental_shacl_cross_domain_graph import (
    qualify_mapping_graph, validate_mapping_graph_selection,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def qualified(domain, entries):
    registry = {}
    candidates = []
    for i, (owner, predicate) in enumerate(entries, 1):
        cid = f"P{i}"
        registry[cid] = {
            "domain": domain, "kind": "property",
            "node_uris": [owner], "edges": [],
            "property": {"owner": owner, "predicate": predicate},
            "owner_shape_uri": owner, "property_predicate_uri": predicate,
        }
        candidates.append({"id": cid, "domain": domain, "kind": "property",
                           "path": f"{owner} → {predicate}"})
    return {"prompt": {"domain": domain, "candidates": candidates},
            "registry": registry}


def mapping(mid, a, b, key="asset"):
    return {"id": mid, "left_domain": a, "right_domain": b,
            "left_property": f"urn:{a}:{key}",
            "right_property": f"urn:{b}:{key}",
            "verified": True}


def fixture():
    domains = {
        "dexpi": qualified("dexpi", [
            ("Equipment", "urn:dexpi:asset"),
            ("ActuatingFunction", "urn:dexpi:asset"),
        ]),
        "ecad": qualified("ecad", [("Device", "urn:ecad:asset")]),
        "engineeringbom": qualified("engineeringbom", [
            ("Part", "urn:engineeringbom:asset"),
            ("Part", "urn:engineeringbom:product"),
        ]),
    }
    mappings = {
        "de": mapping("de", "dexpi", "ecad"),
        "eb": mapping("eb", "ecad", "engineeringbom"),
        "dp": mapping("dp", "dexpi", "engineeringbom", "product"),
    }
    return mappings, domains


def test_preserves_multiple_owners_and_n_domain_edges():
    mappings, domains = fixture()
    offered = qualify_mapping_graph(mappings, domains)
    assert [e["id"] for e in offered["mapping_candidates"]] == ["de", "eb"]
    assert offered["mapping_candidates"][0]["left_identifier_candidate_ids"] == [
        "dexpi:P1", "dexpi:P2"]
    assert len(offered["identifier_path_candidates"]) == 4


def test_validates_connected_three_domain_selection():
    mappings, domains = fixture()
    offered = qualify_mapping_graph(mappings, domains)
    assert [m["id"] for m in validate_mapping_graph_selection(
        ["de", "eb"],
        ["dexpi:P1", "ecad:P1", "engineeringbom:P1"],
        offered, mappings,
    )] == ["de", "eb"]


def test_rejects_missing_endpoint():
    mappings, domains = fixture()
    offered = qualify_mapping_graph(mappings, domains)
    with pytest.raises(SelectionContractError, match="endpoints"):
        validate_mapping_graph_selection(["de"], ["dexpi:P1"], offered, mappings)


def test_rejects_unoffered_mapping():
    mappings, domains = fixture()
    offered = qualify_mapping_graph(mappings, domains)
    with pytest.raises(SelectionContractError, match="not offered"):
        validate_mapping_graph_selection(
            ["dp"], ["dexpi:P1", "engineeringbom:P1"], offered, mappings)


def test_rejects_dangling_identifier():
    mappings, domains = fixture()
    offered = qualify_mapping_graph(mappings, domains)
    with pytest.raises(SelectionContractError, match="no mapping edge"):
        validate_mapping_graph_selection(
            ["de"], ["dexpi:P1", "ecad:P1", "engineeringbom:P1"], offered, mappings)


def test_rejects_unverified_mapping():
    mappings, domains = fixture()
    mappings["de"]["verified"] = False
    assert [e["id"] for e in qualify_mapping_graph(mappings, domains)["mapping_candidates"]] == ["eb"]


def test_rejects_wrong_domain_registry():
    mappings, domains = fixture()
    domains["ecad"]["prompt"]["domain"] = "dexpi"
    with pytest.raises(SelectionContractError, match="domain mismatch"):
        qualify_mapping_graph(mappings, domains)


def test_rejects_tampered_owner():
    mappings, domains = fixture()
    domains["dexpi"]["registry"]["P1"]["owner_shape_uri"] = "Other"
    with pytest.raises(SelectionContractError, match="Malformed"):
        qualify_mapping_graph(mappings, domains)


def test_rejects_disconnected_selected_graph():
    mappings, domains = fixture()
    domains["productcatalog"] = qualified("productcatalog", [
        ("CatalogProduct", "urn:productcatalog:product")])
    domains["assetinventory"] = qualified("assetinventory", [
        ("InventoryItem", "urn:assetinventory:product")])
    mappings["ap"] = mapping("ap", "assetinventory", "productcatalog", "product")
    offered = qualify_mapping_graph(mappings, domains)
    with pytest.raises(SelectionContractError, match="disconnected"):
        validate_mapping_graph_selection(
            ["de", "ap"],
            ["dexpi:P1", "ecad:P1", "assetinventory:P1", "productcatalog:P1"],
            offered, mappings)


def test_explicit_empty_owner_policy_offers_no_mapping():
    mappings, domains = fixture()
    mappings["de"]["approved_owner_pairs"] = []
    offered = qualify_mapping_graph(mappings, domains)
    assert [e["id"] for e in offered["mapping_candidates"]] == ["eb"]
    assert "dexpi:P1" not in {
        c["id"] for c in offered["identifier_path_candidates"]
    }


def test_only_explicitly_approved_owner_pair_is_offered():
    mappings, domains = fixture()
    mappings["de"]["approved_owner_pairs"] = [{
        "left_owner_shape_uri": "Equipment",
        "right_owner_shape_uri": "Device",
        "evidence_ids": ["urn:approval:equipment-device"],
    }]
    offered = qualify_mapping_graph(mappings, domains)
    edge = next(e for e in offered["mapping_candidates"] if e["id"] == "de")
    assert edge["left_identifier_candidate_ids"] == ["dexpi:P1"]
    assert edge["right_identifier_candidate_ids"] == ["ecad:P1"]
    assert edge["approved_owner_pair_candidate_ids"] == [
        {"left_id": "dexpi:P1", "right_id": "ecad:P1"}
    ]
    assert [m["id"] for m in validate_mapping_graph_selection(
        ["de"], ["dexpi:P1", "ecad:P1"], offered, mappings
    )] == ["de"]


def test_unqualified_approved_pair_cannot_be_offered():
    mappings, domains = fixture()
    mappings["de"]["approved_owner_pairs"] = [{
        "left_owner_shape_uri": "InventedShape",
        "right_owner_shape_uri": "Device",
        "evidence_ids": ["urn:approval:invented"],
    }]
    offered = qualify_mapping_graph(mappings, domains)
    assert not any(e["id"] == "de" for e in offered["mapping_candidates"])


def test_tampered_owner_pair_candidate_is_rejected():
    mappings, domains = fixture()
    mappings["de"]["approved_owner_pairs"] = [{
        "left_owner_shape_uri": "Equipment",
        "right_owner_shape_uri": "Device",
        "evidence_ids": ["urn:approval:equipment-device"],
    }]
    offered = qualify_mapping_graph(mappings, domains)
    edge = next(e for e in offered["mapping_candidates"] if e["id"] == "de")
    edge["left_identifier_candidate_ids"].append("dexpi:P2")
    edge["approved_owner_pair_candidate_ids"].append({
        "left_id": "dexpi:P2", "right_id": "ecad:P1"
    })
    with pytest.raises(SelectionContractError, match="not approved|differs"):
        validate_mapping_graph_selection(
            ["de"], ["dexpi:P2", "ecad:P1"], offered, mappings
        )


def test_disallowed_cross_product_of_approved_pairs_rejected():
    mappings, domains = fixture()
    domains["ecad"] = qualified("ecad", [
        ("Device", "urn:ecad:asset"), ("Symbol", "urn:ecad:asset")
    ])
    mappings["de"]["approved_owner_pairs"] = [
        {"left_owner_shape_uri": "Equipment", "right_owner_shape_uri": "Device",
         "evidence_ids": ["urn:approval:1"]},
        {"left_owner_shape_uri": "ActuatingFunction", "right_owner_shape_uri": "Symbol",
         "evidence_ids": ["urn:approval:2"]},
    ]
    offered = qualify_mapping_graph(mappings, domains)
    with pytest.raises(SelectionContractError, match="not approved"):
        validate_mapping_graph_selection(
            ["de"], ["dexpi:P1", "ecad:P2"], offered, mappings
        )
