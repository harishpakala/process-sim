import json
import shutil
from pathlib import Path

import pytest

from selira.runtime.contract_registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


def test_registry_inventory():
    entries = load_registry(ROOT)
    assert {e["id"] for e in entries} == {
        "SC-01", "SC-02", "SC-03", "SC-04", "LP-03", "LP-04"
    }


@pytest.mark.parametrize("fault", [
    "duplicate", "missing_file", "bad_backend", "bad_activation",
    "bad_binding_id", "bad_enabled", "path_escape", "bad_schema"
])
def test_invalid_registry(tmp_path, fault):
    for directory in ("registry", "contracts", "policies", "bindings"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    path = tmp_path / "registry" / "contract_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data["contracts"]
    if fault == "duplicate":
        entries.append(entries[0])
    elif fault == "missing_file":
        entries[0]["specification"] = "missing.safsl"
    elif fault == "bad_backend":
        entries[0]["backend"] = "unknown"
    elif fault == "bad_activation":
        entries[-1]["activation"] = {}
    elif fault == "bad_binding_id":
        entries[-1]["binding"] = "bindings/LP-03.json"
    elif fault == "bad_enabled":
        entries[0]["enabled"] = "true"
    elif fault == "path_escape":
        entries[0]["specification"] = "../outside.safsl"
    elif fault == "bad_schema":
        data["schema_version"] = "99"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(tmp_path)
