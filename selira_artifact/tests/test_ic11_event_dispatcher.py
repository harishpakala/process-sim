from pathlib import Path

import pytest

from selira.runtime.contract_registry import load_registry
from selira.runtime.event_dispatcher import EventDispatcher

ROOT = Path(__file__).resolve().parents[1]


def entry(key, event, produces, enabled=True):
    return {"id": key, "kind": "LP", "enabled": enabled,
            "activation": {"event": event, "scope": "per_contract_instance"},
            "produces": produces}


def test_registered_chain():
    dispatcher = EventDispatcher(load_registry(ROOT))
    context = {"dependency.changed": True}

    def execute(policy, data):
        if policy["id"] == "LP-03":
            return {"assessment.affected": data["dependency.changed"]}
        assert policy["id"] == "LP-04"
        return {"selection.reassess": data["assessment.affected"]}

    result, trace = dispatcher.dispatch(
        "DependencyProjectionCompleted", context, execute)
    assert result["selection.reassess"] is True
    assert trace == (("DependencyProjectionCompleted", "LP-03"),
                     ("ChangeImpactAssessed", "LP-04"))
    assert context == {"dependency.changed": True}


def test_order_and_disabled():
    dispatcher = EventDispatcher([
        entry("B", "start", "b"), entry("A", "start", "a"),
        entry("C", "start", "c", False)])
    result, trace = dispatcher.dispatch(
        "start", {}, lambda p, c: {p["id"]: True})
    assert trace == (("start", "B"), ("start", "A"))
    assert result == {"B": True, "A": True}


@pytest.mark.parametrize("entries", [
    [entry("A", "start", "start")],
    [entry("A", "start", "next"), entry("B", "next", "start")],
])
def test_cycles(entries):
    with pytest.raises(ValueError, match="Cyclic"):
        EventDispatcher(entries)


def test_unknown_event():
    dispatcher = EventDispatcher([])
    assert dispatcher.dispatch("unknown", {"x": True}, None) == (
        {"x": True}, ())


def test_overwrite():
    dispatcher = EventDispatcher([entry("A", "start", "end")])
    with pytest.raises(ValueError, match="overwrites"):
        dispatcher.dispatch("start", {"x": True}, lambda p, c: {"x": False})


def test_repeated_event():
    dispatcher = EventDispatcher([
        entry("A", "start", "end"), entry("B", "start", "end")])
    with pytest.raises(ValueError, match="repeated event"):
        dispatcher.dispatch("start", {}, lambda p, c: {p["id"]: True})


def test_execution_failure():
    dispatcher = EventDispatcher([
        entry("A", "start", "next"), entry("B", "next", "end")])
    context = {"x": True}

    def execute(policy, data):
        if policy["id"] == "A":
            return {"y": True}
        raise ValueError("Missing data")

    with pytest.raises(ValueError, match="Missing data"):
        dispatcher.dispatch("start", context, execute)
    assert context == {"x": True}
