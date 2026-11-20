"""N-domain Qwen contract tests; transport is injected, no Ollama required."""
import json

import pytest

from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    prepare_n_domain_selection, validate_n_domain_selection, select_n_domain_with_ollama,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def fixture():
    qualified = {}
    for domain in ("dexpi", "ecad", "engineeringbom"):
        predicate = f"urn:{domain}:asset"
        owner = f"urn:{domain}:Owner"
        qualified[domain] = {
            "prompt": {"domain": domain, "candidates": [
                {"id": "R1", "domain": domain, "kind": "result",
                 "path": f"{domain} → Owner"},
                {"id": "P1", "domain": domain, "kind": "property",
                 "path": f"{domain} → Owner → AssetIdentifier"},
            ]},
            "registry": {
                "R1": {"domain": domain, "kind": "result",
                       "node_uris": [owner], "edges": [],
                       "target_shape_uri": owner},
                "P1": {"domain": domain, "kind": "property",
                       "node_uris": [owner], "edges": [],
                       "property": {"owner": owner, "predicate": predicate},
                       "owner_shape_uri": owner,
                       "property_predicate_uri": predicate},
            },
        }
    mappings = {}
    for mid, left, right in (("de", "dexpi", "ecad"),
                             ("eb", "ecad", "engineeringbom")):
        mappings[mid] = {
            "id": mid, "left_domain": left, "right_domain": right,
            "left_property": f"urn:{left}:asset",
            "right_property": f"urn:{right}:asset", "verified": True,
        }
    return prepare_n_domain_selection("Show matching entities", qualified, mappings)


def selected():
    return {
        "status": "selected",
        "result_ids": ["dexpi:R1", "engineeringbom:R1"],
        "identifier_path_ids": ["dexpi:P1", "ecad:P1", "engineeringbom:P1"],
        "mapping_ids": ["de", "eb"],
        "reason": "Both mappings connect the requested result domains",
    }


def test_payload_preserves_scoped_candidates_and_edges():
    prompt = fixture()["prompt"]
    assert len(prompt["result_candidates"]) == 6
    assert len(prompt["identifier_path_candidates"]) == 3
    assert [m["id"] for m in prompt["mapping_candidates"]] == ["de", "eb"]


def test_valid_three_domain_selection():
    assert validate_n_domain_selection(json.dumps(selected()), fixture()) == selected()


def test_qwen_transport_receives_all_three_groups():
    captured = {}
    def transport(url, payload, timeout):
        captured.update(payload)
        return {"message": {"content": json.dumps(selected())}}
    assert select_n_domain_with_ollama(fixture(), transport=transport) == selected()
    user_payload = json.loads(captured["messages"][1]["content"])
    assert set(user_payload) == {"question", "result_candidates",
                                 "identifier_path_candidates", "mapping_candidates"}


@pytest.mark.parametrize("change", [
    {"result_ids": ["invented:R1"]},
    {"identifier_path_ids": ["dexpi:P1", "engineeringbom:P1"]},
    {"mapping_ids": ["invented"]},
    {"mapping_ids": ["de"]},
    {"result_ids": []},
    {"status": "ambiguous"},
    {"status": "unresolved"},
    {"reason": ""},
    {"result_ids": ["dexpi:R1", "dexpi:R1"]},
])
def test_rejects_invalid_selected_responses(change):
    response = {**selected(), **change}
    with pytest.raises(SelectionContractError):
        validate_n_domain_selection(response, fixture())


def test_uncertainty_requires_no_ids():
    response = {"status": "ambiguous", "result_ids": [],
                "identifier_path_ids": [], "mapping_ids": [],
                "reason": "Owner is not specified"}
    assert validate_n_domain_selection(response, fixture()) == response


def test_extra_fields_fail_closed():
    with pytest.raises(SelectionContractError):
        validate_n_domain_selection({**selected(), "sparql": "SELECT * {}"}, fixture())


def test_result_outside_mapping_graph_fails():
    response = selected()
    response["mapping_ids"] = ["de"]
    response["identifier_path_ids"] = ["dexpi:P1", "ecad:P1"]
    with pytest.raises(SelectionContractError, match="outside selected"):
        validate_n_domain_selection(response, fixture())
