import json
from pathlib import Path

import pytest

from selira.runtime.policy_evaluator import load_policy, evaluate_policy
from selira.runtime.runtime_binding import (
    validate_binding, resolve_inputs, bind_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


def policy(name):
    return (load_policy(ROOT / "policies" / f"{name}.safsl"),
            json.loads((ROOT / "bindings" / f"{name}.json").read_text()))


def test_policy_chain():
    impact, ib = policy("LP-03")
    selection, sb = policy("LP-04")
    context = {point: True for point in ib["inputs"].values()}
    for changed in (False, True):
        context["dependency.changed"] = changed
        decision = evaluate_policy(impact, resolve_inputs(impact, ib, context))
        updated = {**context, **bind_outputs(impact, ib, decision)}
        outputs = evaluate_policy(selection, resolve_inputs(selection, sb, updated))
        assert bind_outputs(selection, sb, outputs) == {
            "selection.reassess": changed, "selection.reuse": not changed
        }


@pytest.mark.parametrize("fault", ["missing", "integer", "none", "string"])
def test_invalid_context(fault):
    process, binding = policy("LP-03")
    context = {point: True for point in binding["inputs"].values()}
    point = next(iter(context))
    if fault == "missing":
        del context[point]
    else:
        context[point] = {"integer": 1, "none": None, "string": "true"}[fault]
    with pytest.raises(ValueError):
        resolve_inputs(process, binding, context)


@pytest.mark.parametrize("fault", ["missing_port", "extra_port", "duplicate_output",
                                   "overwrite_input"])
def test_invalid_binding(fault):
    process, binding = policy("LP-04")
    if fault == "missing_port":
        del binding["inputs"]["Affected"]
    elif fault == "extra_port":
        binding["inputs"]["Unknown"] = "unknown"
    elif fault == "duplicate_output":
        binding["outputs"]["Reuse"] = binding["outputs"]["Reassess"]
    else:
        binding["outputs"]["Reuse"] = binding["inputs"]["Affected"]
    with pytest.raises(ValueError):
        validate_binding(process, binding)


@pytest.mark.parametrize("outputs", [
    {"Reassess": True},
    {"Reassess": True, "Reuse": 0},
    {"Reassess": True, "Reuse": False, "Extra": True},
])
def test_invalid_outputs(outputs):
    process, binding = policy("LP-04")
    with pytest.raises(ValueError):
        bind_outputs(process, binding, outputs)
