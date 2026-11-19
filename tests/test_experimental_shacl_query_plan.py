"""Offline Phase 1 query-plan validation tests."""
import copy
import json

import pytest

from process_sim.dtwise.experimental_shacl_query_plan import validate_query_plan
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


@pytest.fixture
def prepared():
    return {
        "prompt": {"candidates": [{"id": "C1", "path": "ECAD → Device → EndPoint → Address"}]},
        "registry": {"C1": {
            "node_uris": ["urn:ECAD", "urn:Device", "urn:EndPoint"],
            "edges": [], "property": {"owner": "urn:EndPoint", "predicate": "urn:Address"},
        }},
    }


def plan(operation="COUNT", kind="node", index=2):
    return {
        "status": "selected", "selected_candidate_ids": ["C1"],
        "operation": operation,
        "target": {"candidate_id": "C1", "node_index": index, "kind": kind},
        "modifiers": [], "reason": "Selected verified path and intent",
    }


@pytest.mark.parametrize("operation,kind,index", [
    ("RETRIEVE", "property", 2), ("COUNT", "node", 2), ("EXISTS", "node", 1),
])
def test_supported_phase1_intents(prepared, operation, kind, index):
    proposed = plan(operation, kind, index)
    assert validate_query_plan(json.dumps(proposed), prepared)["operation"] == operation


@pytest.mark.parametrize("status", ["ambiguous", "unresolved"])
def test_uncertainty_has_no_operation_or_target(prepared, status):
    proposed = {
        "status": status, "selected_candidate_ids": [], "operation": None,
        "target": None, "modifiers": [], "reason": "Cannot decide",
    }
    assert validate_query_plan(proposed, prepared)["status"] == status


@pytest.mark.parametrize("change", [
    {"operation": "SUM"}, {"operation": "FILTER"},
    {"modifiers": [{"type": "FILTER_EQUALS"}]},
    {"selected_candidate_ids": ["C99"]},
    {"target": {"candidate_id": "C99", "node_index": 2, "kind": "node"}},
    {"target": {"candidate_id": "C1", "node_index": 9, "kind": "node"}},
    {"target": {"candidate_id": "C1", "node_index": True, "kind": "node"}},
    {"target": {"candidate_id": "C1", "node_index": 1, "kind": "property"}},
    {"target": {"candidate_id": "C1", "node_index": 2, "kind": "unknown"}},
    {"target": None}, {"operation": None},
])
def test_reject_invalid_plans(prepared, change):
    proposed = plan()
    proposed.update(change)
    with pytest.raises(SelectionContractError):
        validate_query_plan(proposed, prepared)


def test_retrieve_cannot_target_node(prepared):
    with pytest.raises(SelectionContractError, match="RETRIEVE"):
        validate_query_plan(plan("RETRIEVE", "node"), prepared)


def test_count_cannot_target_property(prepared):
    with pytest.raises(SelectionContractError, match="node target"):
        validate_query_plan(plan("COUNT", "property"), prepared)


def test_reject_llm_authored_sparql(prepared):
    proposed = plan()
    proposed["sparql"] = "DELETE WHERE { ?s ?p ?o }"
    with pytest.raises(SelectionContractError, match="unexpected"):
        validate_query_plan(proposed, prepared)


def test_uncertain_plan_cannot_hide_operation(prepared):
    proposed = plan()
    proposed.update(status="unresolved", selected_candidate_ids=[])
    with pytest.raises(SelectionContractError):
        validate_query_plan(proposed, prepared)
