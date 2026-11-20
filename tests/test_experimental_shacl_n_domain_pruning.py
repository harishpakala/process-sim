"""Conservative SHACL-vocabulary candidate pruning regression tests."""
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    _prune_explicit_candidates, compact_n_domain_prompt,
)


def candidates():
    paths = [
        {"id": "dexpi:P1", "domain": "dexpi", "path": "Equipment → AssetIdentifier"},
        {"id": "dexpi:P2", "domain": "dexpi", "path": "ActuatingFunction → AssetIdentifier"},
        {"id": "ecad:P1", "domain": "ecad", "path": "Device → AssetIdentifier"},
        {"id": "ecad:P2", "domain": "ecad", "path": "Symbol → AssetIdentifier"},
    ]
    edge = {
        "id": "de", "left_domain": "dexpi", "right_domain": "ecad",
        "left_identifier_candidate_ids": ["dexpi:P1", "dexpi:P2"],
        "right_identifier_candidate_ids": ["ecad:P1", "ecad:P2"],
        "join_alternatives": [
            {"left_id": a, "right_id": b}
            for a in ("dexpi:P1", "dexpi:P2")
            for b in ("ecad:P1", "ecad:P2")
        ],
        "approved_owner_pair_candidate_ids": None,
    }
    results = [
        {"id": "dexpi:R1", "domain": "dexpi", "path": "Equipment"},
        {"id": "dexpi:R2", "domain": "dexpi", "path": "ActuatingFunction"},
        {"id": "ecad:R1", "domain": "ecad", "path": "Device"},
        {"id": "ecad:R2", "domain": "ecad", "path": "Symbol"},
    ]
    return results, {"identifier_path_candidates": paths, "mapping_candidates": [edge]}


def test_explicit_owners_reduce_to_one_join():
    results, graph = candidates()
    narrowed, offered = _prune_explicit_candidates(
        "Find DEXPI Equipment and ECAD Device using AssetIdentifier.", results, graph
    )
    assert {r["id"] for r in narrowed} == {"dexpi:R1", "ecad:R1"}
    assert len(offered["mapping_candidates"][0]["join_alternatives"]) == 1
    assert {p["id"] for p in offered["identifier_path_candidates"]} == {
        "dexpi:P1", "ecad:P1"
    }


def test_implicit_owners_preserve_alternatives():
    results, graph = candidates()
    narrowed, offered = _prune_explicit_candidates(
        "Find corresponding DEXPI and ECAD entities using AssetIdentifier.", results, graph
    )
    assert len(narrowed) == 4
    assert len(offered["mapping_candidates"][0]["join_alternatives"]) == 4


def test_explicit_unsupported_identifier_removes_asset_bridge():
    results, graph = candidates()
    narrowed, offered = _prune_explicit_candidates(
        "Use ProductIdentifier only; do not use AssetIdentifier.", results, graph
    )
    assert offered["mapping_candidates"] == []
    assert offered["identifier_path_candidates"] == []


def test_partial_owner_label_does_not_match_identifier():
    results, graph = candidates()
    _, offered = _prune_explicit_candidates(
        "Match an Asset across domains.", results, graph
    )
    assert len(offered["mapping_candidates"][0]["join_alternatives"]) == 4


def test_compact_prompt_identifier_owner_uses_immediate_shacl_parent():
    prompt = compact_n_domain_prompt({
        "question": "Count ECAD Device with matching DEXPI Equipment using AssetIdentifier.",
        "result_candidates": [
            {"id": "ecad:R2", "domain": "ecad", "kind": "result", "path": "ECAD → Device"},
            {"id": "dexpi:R3", "domain": "dexpi", "kind": "result", "path": "DEXPI → Equipment"},
        ],
        "identifier_path_candidates": [
            {"id": "ecad:P1", "domain": "ecad", "path": "ECAD → Device → AssetIdentifier"},
            {"id": "dexpi:P7", "domain": "dexpi", "path": "DEXPI → Equipment → AssetIdentifier"},
        ],
        "mapping_candidates": [{
            "id": "dexpi-ecad-asset-identifier",
            "left_domain": "dexpi", "right_domain": "ecad",
            "join_alternatives": [{"left_id": "dexpi:P7", "right_id": "ecad:P1"}],
        }],
    })
    assert {p["id"]: (p["owner"], p["property"]) for p in prompt["identifiers"]} == {
        "ecad:P1": ("Device", "AssetIdentifier"),
        "dexpi:P7": ("Equipment", "AssetIdentifier"),
    }
    assert prompt["mappings"][0]["allowed_pairs"] == [["dexpi:P7", "ecad:P1"]]
