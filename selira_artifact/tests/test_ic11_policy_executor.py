import json
import shutil
from itertools import product
from pathlib import Path

import pytest

from selira.runtime.policy_executor import PolicyExecutor

ROOT = Path(__file__).resolve().parents[1]
EVENT = "DependencyProjectionCompleted"


def context(c=True, p=True, a=True, d=False):
    return {"evidence.coverage_attested": c,
            "context.policy_unchanged": p,
            "context.authority_unchanged": a,
            "dependency.changed": d}


@pytest.mark.parametrize("bits", list(product([False, True], repeat=4)))
def test_registered_execution(bits):
    executor = PolicyExecutor(ROOT)
    c, p, a, d = bits
    initial = context(*bits)
    result, trace = executor.dispatch(EVENT, initial)
    affected = not (c and p and a) or d
    assert result["assessment.affected"] is affected
    assert result["selection.reassess"] is affected
    assert result["selection.reuse"] is not affected
    assert len(trace) == 2
    assert initial == context(*bits)


def test_missing_input():
    executor = PolicyExecutor(ROOT)
    initial = context()
    del initial["dependency.changed"]
    with pytest.raises(ValueError, match="Missing or invalid"):
        executor.dispatch(EVENT, initial)


@pytest.fixture
def configured_root(tmp_path):
    for directory in ("registry", "contracts", "policies", "bindings"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    return tmp_path


def test_renamed_policy_and_port(configured_root):
    root = configured_root
    path = root / "registry" / "contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = next(e for e in data["contracts"] if e["id"] == "LP-03")
    entry["id"] = "ImpactPolicy"
    path.write_text(json.dumps(data), encoding="utf-8")
    path = root / entry["binding"]
    binding = json.loads(path.read_text(encoding="utf-8"))
    binding["policy_id"] = entry["id"]
    binding["inputs"]["Changed"] = binding["inputs"].pop("RelevantDependencyChanged")
    path.write_text(json.dumps(binding), encoding="utf-8")
    path = root / entry["specification"]
    path.write_text(path.read_text(encoding="utf-8").replace(
        "RelevantDependencyChanged", "Changed"), encoding="utf-8")
    result, trace = PolicyExecutor(root).dispatch(EVENT, context(d=True))
    assert result["selection.reassess"] is True
    assert trace[0][1] == "ImpactPolicy"


def test_invalid_interface(configured_root):
    path = configured_root / "bindings" / "LP-03.json"
    binding = json.loads(path.read_text(encoding="utf-8"))
    del binding["inputs"]["RelevantDependencyChanged"]
    path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(ValueError, match="port binding"):
        PolicyExecutor(configured_root)


def test_unregistered_event():
    initial = context()
    assert PolicyExecutor(ROOT).dispatch("UnregisteredEvent", initial) == (
        initial, ())
