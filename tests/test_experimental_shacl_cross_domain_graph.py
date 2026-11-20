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
