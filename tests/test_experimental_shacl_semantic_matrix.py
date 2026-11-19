"""Regression matrix for semantic retrieval -> SHACL candidates -> selection.

Offline deterministic tests exercise the selection contract with mocked Ollama.
They do not measure the semantic accuracy of a real Qwen model.
"""
import pytest

from process_sim.dtwise.experimental_shacl_semantic_candidates import semantic_candidates
from process_sim.dtwise.experimental_shacl_selection import (
    SelectionContractError, validate_selection,
)
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_subgraph import load_index
from pathlib import Path


INDEX = (Path(__file__).resolve().parents[1] /
         "semantic/ontology2/dtwise/dtwise-schema-index.json")


def _prepared(question):
    index = load_index(INDEX, domain="ecad")

    def embeddings(url, payload, timeout):
        assert url.endswith("/api/embed")
        vectors = [[1.0, 0.0]]
        for term in payload["input"][1:]:
            label = term.split(".", 1)[0]
            relevant = any(name in label for name in (
                "ECAD", "Device", "EndPoint", "PLCEndPoint", "Address",
            ))
            vectors.append([1.0, 0.0] if relevant else [0.0, 1.0])
        return {"embeddings": vectors}

    return semantic_candidates(index, question, transport=embeddings)


def _reply(prepared, status, paths):
    ids = [item["id"] for item in prepared["prompt"]["candidates"]
           if item["path"] in paths]
    assert len(ids) == len(paths)
    import json
    response = {"status": status, "selected_candidate_ids": ids,
                "reason": "Mocked semantic interpretation for regression"}
    def chat(url, payload, timeout):
        assert url.endswith("/api/chat")
        assert json.loads(payload["messages"][1]["content"]) == prepared["prompt"]
        return {"message": {"content": json.dumps(response)}}
    return validate_selection(ollama_select(prepared["prompt"], transport=chat),
                              prepared)


DEVICE_ENDPOINT = "ECAD → Device → EndPoint → Address"
DEVICE_PLC = "ECAD → Device → PLCEndPoint → Address"


@pytest.mark.parametrize("question,status,paths", [
    ("Show Address of EndPoint belonging to Device in ECAD",
     "selected", [DEVICE_ENDPOINT]),
    ("Find the network addresses of connection points attached to devices in ECAD",
     "selected", [DEVICE_ENDPOINT, DEVICE_PLC]),
    ("Show Address in ECAD", "ambiguous", []),
    ("Show Address of both EndPoint and PLCEndPoint belonging to Device in ECAD",
     "selected", [DEVICE_ENDPOINT, DEVICE_PLC]),
    ("Show the nonexistent QuantumFluxCode property of Device in ECAD",
     "unresolved", []),
])
def test_semantic_selection_contract_matrix(question, status, paths):
    prepared = _prepared(question)
    assert DEVICE_ENDPOINT in {c["path"] for c in prepared["prompt"]["candidates"]}
    assert DEVICE_PLC in {c["path"] for c in prepared["prompt"]["candidates"]}
    result = _reply(prepared, status, paths)
    assert result["status"] == status
    assert {next(c["path"] for c in prepared["prompt"]["candidates"]
                 if c["id"] == candidate_id)
            for candidate_id in result["selected_candidate_ids"]} == set(paths)


def test_unsupported_property_can_still_have_embedding_candidates():
    """Document current gap: nearest-neighbor retrieval is not an existence test."""
    prepared = _prepared("Show the nonexistent QuantumFluxCode property of Device in ECAD")
    assert prepared["prompt"]["candidates"]
    assert all("QuantumFluxCode" not in item["path"]
               for item in prepared["prompt"]["candidates"])
    # Contract validation alone cannot reject a semantically wrong known ID.
    known = prepared["prompt"]["candidates"][0]["id"]
    assert validate_selection({
        "status": "selected", "selected_candidate_ids": [known],
        "reason": "A plausible but semantically incorrect selection",
    }, prepared)["status"] == "selected"


def test_semantic_selection_rejects_unoffered_candidate_id():
    prepared = _prepared("Show Address in ECAD")
    with pytest.raises(SelectionContractError, match="Unknown candidate ID"):
        validate_selection({
            "status": "selected", "selected_candidate_ids": ["NOT_OFFERED"],
            "reason": "Invalid candidate",
        }, prepared)
