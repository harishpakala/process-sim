import json
import shutil
from pathlib import Path

import pytest

from selira.runtime.automation_manager import MultiContractAutomationManager
from test_ic10_ported_manager import fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def configured_root(tmp_path):
    for folder in ("registry", "contracts", "policies", "bindings"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    return tmp_path


@pytest.mark.parametrize("backend", ["ast", "sparql"])
def test_manager_registry(configured_root, backend):
    path = configured_root / "registry" / "contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data["contracts"]:
        if entry["kind"] == "LP":
            entry["backend"] = backend
    path.write_text(json.dumps(data), encoding="utf-8")
    manager = MultiContractAutomationManager.from_directory(configured_root)
    _, graph, flags = fixture()
    assert manager.submit(graph, expected_version=0, **flags)["committed"]
    result = manager.submit(graph, expected_version=1, **flags,
                            coverage_attested=True, policy_unchanged=True,
                            authority_unchanged=True)
    assert result["committed"]
    assert result["reassessment"]["selective_evaluations"] == 0
    assert result["reassessment"]["equivalent"]


def test_missing_selection_defers(configured_root):
    path = configured_root / "registry" / "contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    next(e for e in data["contracts"] if e["id"] == "LP-04")["enabled"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    manager = MultiContractAutomationManager.from_directory(configured_root)
    _, graph, flags = fixture()
    assert manager.submit(graph, expected_version=0, **flags)["committed"]
    result = manager.submit(graph, expected_version=1, **flags)
    assert result["verdict"] == "U"
    assert not result["committed"]
    assert manager.store.snapshot()[1] == 1


def test_disabled_structural_contract(configured_root):
    path = configured_root / "registry" / "contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    next(e for e in data["contracts"] if e["id"] == "SC-04")["enabled"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    manager = MultiContractAutomationManager.from_directory(configured_root)
    _, graph, flags = fixture()
    result = manager.submit(graph, expected_version=0, **flags)
    assert result["committed"]
    assert {r["id"] for r in result["contracts"].values()} == {
        "SC_01", "SC_02", "SC_03"}
