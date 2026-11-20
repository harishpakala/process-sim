"""Opt-in local Ollama smoke test: exactly one cross-domain paraphrase question.

Run: RUN_SHACL_LIVE_QWEN=1 pytest -q tests/test_shacl_cross_domain_select_live.py
Requires local Ollama and the repository schema/mapping files.
"""
import json
import os
from pathlib import Path

import pytest

QUESTION = (
    "Retrieve up to five ECAD Devices paired with their corresponding DEXPI "
    "Equipment through the shared AssetIdentifier, sorting the results by "
    "the ECAD Device's LocalId from lowest to highest."
)


@pytest.mark.skipif(os.environ.get("RUN_SHACL_LIVE_QWEN") != "1",
                    reason="Live Qwen smoke test is opt-in")
def test_one_live_cross_domain_paraphrase(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    questions = tmp_path / "questions.json"
    output = tmp_path / "output.json"
    questions.write_text(json.dumps([QUESTION]), encoding="utf-8")
    completed = subprocess.run([
        sys.executable, "-m",
        "process_sim.dtwise.shacl_planner.standalone_shacl_query_planner",
        "--schema", str(root / "semantic/ontology2/dtwise/dtwise-schema-index.json"),
        "--questions", str(questions), "--retrieval", "expanded",
        "--output", str(output),
    ], cwd=root, capture_output=True, text=True, timeout=240)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    records = json.loads(output.read_text(encoding="utf-8"))
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "valid_response", record
    assert record["qwen_calls"] == 1
    answer = record["answer"]
    assert len(answer["projection_ids"]) == 2
    assert {pid.split(":")[0] for pid in answer["projection_ids"]} == {"ecad", "dexpi"}
    assert answer["filters"] == []
    assert answer["boolean_operator"] == "NONE"
    assert answer["join"] is True
    assert answer["limit"] == 5
    assert len(answer["order_by"]) == 1
    assert answer["order_by"][0]["direction"] == "ASC"
    assert answer["mapping_ids"] == ["dexpi-ecad-asset-identifier"]
    assert len(answer["identifier_path_ids"]) == 2
    assert not record.get("validation_errors")
