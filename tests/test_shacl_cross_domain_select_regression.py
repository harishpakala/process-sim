"""Deterministic Phase-1 cross-domain SELECT regression contracts.

No Ollama, embeddings, SPARQL, or hardcoded natural-language parser templates.
Candidate IDs are synthetic and local to these tests.
"""
import pytest

from process_sim.dtwise.experimental_shacl_cross_domain_graph import qualify_mapping_graph
from process_sim.dtwise.shacl_planner.cross_domain_phase1 import _cross_validate
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import (
    _explicit_limit, _explicit_sort,
)


def _fixture():
    owners = {"ecad": "urn:ecad:Device", "dexpi": "urn:dexpi:Equipment"}
    entries = {
        "ecad": [("P1", "AssetIdentifier"), ("P2", "DeviceType"), ("P3", "LocalId")],
        "dexpi": [("P1", "AssetIdentifier"), ("P2", "LocalId")],
    }
    qualified = {}
    candidates = []
    for domain, properties in entries.items():
        owner = owners[domain]
        registry = {"R1": {"domain": domain, "kind": "result", "node_uris": [owner]}}
        offered = [{"id": "R1", "kind": "result", "domain": domain,
                    "path": f"{domain} -> {owner}"}]
        candidates.append({**offered[0], "id": f"{domain}:R1", "node_uris": [owner]})
        for pid, name in properties:
            predicate = f"urn:{domain}:{name}"
            registry[pid] = {
                "domain": domain, "kind": "property", "node_uris": [owner],
                "property": {"owner": owner, "predicate": predicate},
                "owner_shape_uri": owner, "property_predicate_uri": predicate,
            }
            offered.append({"id": pid, "kind": "property", "domain": domain,
                            "path": f"{domain} -> {owner} -> {name}"})
            candidates.append({**offered[-1], "id": f"{domain}:{pid}",
                               "node_uris": [owner], "property_name": name})
        qualified[domain] = {"prompt": {"domain": domain, "candidates": offered},
                             "registry": registry}
    mappings = {"asset": {
        "id": "asset", "left_domain": "dexpi", "right_domain": "ecad",
        "left_property": "urn:dexpi:AssetIdentifier",
        "right_property": "urn:ecad:AssetIdentifier", "verified": True,
    }}
    graph = qualify_mapping_graph(mappings, qualified)
    return candidates, graph, mappings, owners


def _plan(**changes):
    plan = {
        "status": "selected", "projection_ids": ["ecad:R1", "dexpi:R1"],
        "existence_ids": [], "filters": [], "boolean_operator": "NONE",
        "join": True, "count_target_id": None, "order_by": [],
        "limit": None, "join_owner_id": None, "reason": "Grounded selection",
        "mapping_ids": ["asset"], "identifier_path_ids": ["dexpi:P1", "ecad:P1"],
    }
    plan.update(changes)
    return plan


CASES = [
    (
        "Show ECAD Device and DEXPI Equipment with matching AssetIdentifier where DeviceType is Sensor.",
        {"filters": [{"property_id": "ecad:P2", "operator": "=", "value": "Sensor"}]},
    ),
    (
        "Show ECAD Device and DEXPI Equipment with matching AssetIdentifier where ECAD Device DeviceType is Sensor AND DEXPI Equipment LocalId is EQ_101.",
        {"filters": [{"property_id": "ecad:P2", "operator": "=", "value": "Sensor"},
                     {"property_id": "dexpi:P2", "operator": "=", "value": "EQ_101"}],
         "boolean_operator": "AND"},
    ),
    (
        "Show ECAD Device and DEXPI Equipment with matching AssetIdentifier where ECAD Device DeviceType is Sensor OR DEXPI Equipment LocalId is EQ_101.",
        {"filters": [{"property_id": "ecad:P2", "operator": "=", "value": "Sensor"},
                     {"property_id": "dexpi:P2", "operator": "=", "value": "EQ_101"}],
         "boolean_operator": "OR"},
    ),
    (
        "Show ECAD Device and DEXPI Equipment with matching AssetIdentifier, ordered by ECAD Device LocalId ascending, limited to 5 results.",
        {"order_by": [{"property_id": "ecad:P3", "direction": "ASC"}], "limit": 5},
    ),
    (
        "Retrieve up to five ECAD Devices paired with their corresponding DEXPI Equipment through the shared AssetIdentifier, sorting the results by the ECAD Device's LocalId from lowest to highest.",
        {"order_by": [{"property_id": "ecad:P3", "direction": "ASC"}], "limit": 5},
    ),
]


def _validate(question, plan):
    candidates, graph, mappings, owners = _fixture()
    return _cross_validate(
        plan, candidates, graph, mappings, ("dexpi", "ecad"), question,
        {domain: {owner} for domain, owner in owners.items()},
        {"ecad": {"deviceType".casefold(), "localid", "assetidentifier"},
         "dexpi": {"localid", "assetidentifier"}},
    )[0]


@pytest.mark.parametrize("question,changes", CASES)
def test_supported_select_contracts(question, changes):
    assert _validate(question, _plan(**changes)) == []


@pytest.mark.parametrize("question,changes", CASES)
def test_requested_result_entity_cannot_be_silently_dropped(question, changes):
    plan = _plan(**changes)
    plan["projection_ids"] = ["ecad:R1"]
    assert any("Explicit dexpi result concepts missing from projections" in error
               for error in _validate(question, plan))


def test_rejects_missing_boolean_operator():
    question, changes = CASES[1]
    plan = _plan(**changes)
    plan["boolean_operator"] = "NONE"
    assert "Multiple filters require Boolean operator" in _validate(question, plan)


def test_rejects_unapproved_mapping():
    question, changes = CASES[0]
    plan = _plan(**changes)
    plan["mapping_ids"] = ["invented"]
    assert any("Invalid cross-domain mapping selection" in error
               for error in _validate(question, plan))


def test_rejects_wrong_identifier_endpoint():
    question, changes = CASES[0]
    plan = _plan(**changes)
    plan["identifier_path_ids"] = ["dexpi:P2", "ecad:P1"]
    assert any("Invalid cross-domain mapping selection" in error
               for error in _validate(question, plan))


def test_rejects_missing_explicit_filter_value():
    question, changes = CASES[0]
    plan = _plan(**changes)
    plan["filters"] = []
    assert any("Missing explicit filter value" in error
               for error in _validate(question, plan))


def test_limit_and_sort_paraphrase_recognition():
    assert _explicit_limit(CASES[4][0]) == 5
    assert _explicit_sort(CASES[4][0]) is not None
