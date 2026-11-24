"""Regression checks for the shared smoke-test planner contract."""
import pytest

from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import (
    validate_output, analyze_plan, _explicit_shacl_comparisons,
)

CANDIDATES = [
    {"id": "R1", "kind": "result", "node_uris": ["ecad", "Device"]},
    {"id": "P1", "kind": "property", "property_name": "LocalId",
     "node_uris": ["ecad", "Device", "LocalId"]},
]


def plan(**updates):
    return dict(status="selected", projection_ids=["R1"], existence_ids=[],
                filters=[], boolean_operator="NONE", join=False,
                count_target_id=None, order_by=[], limit=None,
                join_owner_id=None, reason="", **{}) | updates


def test_selected_empty_reason():
    assert not validate_output(plan(), CANDIDATES)


def test_abstention_requires_reason():
    assert validate_output(plan(status="unresolved", projection_ids=[]), CANDIDATES)


def test_property_not_allowed_as_existence():
    assert "Invalid existence_ids" in validate_output(
        plan(existence_ids=["P1"]), CANDIDATES)


@pytest.mark.parametrize("phrase,operator", [
    ("is", "="), ("is not", "!="), ("greater than", ">"),
    ("less than", "<"), ("greater than or equal to", ">="),
    ("less than or equal to", "<="),
])
def test_explicit_comparison(phrase, operator):
    question = f"Show Device where LocalId {phrase} X."
    assert _explicit_shacl_comparisons(question, CANDIDATES) == [
        ("localid", operator, "X")]


def test_wrong_operator_rejected():
    answer = plan(filters=[{"property_id": "P1", "operator": "!=", "value": "X"}])
    errors = analyze_plan(answer, CANDIDATES, "Show Device where LocalId is X.")["errors"]
    assert any("mismatched WHERE comparison" in error for error in errors)


def test_correct_operator_accepted():
    answer = plan(filters=[{"property_id": "P1", "operator": "=", "value": "X"}])
    assert not analyze_plan(answer, CANDIDATES, "Show Device where LocalId is X.")["errors"]


@pytest.mark.parametrize("question,expected", [
    ("Show LocalId is assigned to each DEXPI Equipment", []),
    ("Show smallest LocalId values first", []),
    ("Show highest LocalId first", []),
    ("Show DeviceType has value Sensor", [("devicetype", "=", "Sensor")]),
    ("Find Equipment whose LocalId is either EQ_101 or EQ_102",
     [("localid", "=", "EQ_101"), ("localid", "=", "EQ_102")]),
])
def test_comparison_prose_regressions(question, expected):
    candidates = CANDIDATES + [{"id": "P2", "kind": "property",
                                "property_name": "DeviceType"}]
    assert _explicit_shacl_comparisons(question, candidates) == expected
