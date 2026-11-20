"""Offline tests for deterministic SPARQL compilation from verified path records."""
import pytest

from process_sim.dtwise.experimental_shacl_sparql import compile_selected_paths
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


ROOT = "https://example.org/ecad/ECAD"
DEVICE = "https://example.org/ecad/Device"
ENDPOINT = "https://example.org/ecad/EndPoint"
ADDRESS = "https://example.org/ecad/hasAddress"


def _prepared():
    return {
        "prompt": {"domain": "ecad", "question": "Show Address of EndPoint belonging to Device in ECAD",
                   "candidates": [{"id": "C1", "path": "ECAD → Device → EndPoint → Address"},
                                  {"id": "C2", "path": "ECAD → Device → PLCEndPoint → Address"}]},
        "registry": {
            "C1": {
                "node_uris": [ROOT, DEVICE, ENDPOINT],
                "edges": [{"from": ROOT, "to": DEVICE, "predicate": "https://example.org/ecad/hasDevice"},
                          {"from": DEVICE, "to": ENDPOINT, "predicate": "https://example.org/ecad/hasEndPoint"}],
                "property": {"owner": ENDPOINT, "predicate": ADDRESS, "name": "Address"},
            },
            "C2": {
                "node_uris": [ROOT, DEVICE, "https://example.org/ecad/PLCEndPoint"],
                "edges": [{"from": ROOT, "to": DEVICE, "predicate": "https://example.org/ecad/hasDevice"},
                          {"from": DEVICE, "to": "https://example.org/ecad/PLCEndPoint",
                           "predicate": "https://example.org/ecad/hasPLCEndPoint"}],
                "property": {"owner": "https://example.org/ecad/PLCEndPoint",
                             "predicate": ADDRESS, "name": "Address"},
            },
        },
    }


def _selection(ids, status="selected"):
    return {"status": status, "selected_candidate_ids": ids, "reason": "Test selection"}


def test_compiles_verified_edges_and_terminal_property():
    queries = compile_selected_paths(_prepared(), _selection(["C1"]))
    assert len(queries) == 1
    assert queries[0]["sparql"] == (
        "SELECT DISTINCT ?value WHERE {\n"
        "  ?n0 <https://example.org/ecad/hasDevice> ?n1 .\n"
        "  ?n1 <https://example.org/ecad/hasEndPoint> ?n2 .\n"
        "  ?n2 <https://example.org/ecad/hasAddress> ?value .\n}"
    )
    assert "rdf:type" not in queries[0]["sparql"]


def test_two_selected_branches_compile_independently():
    queries = compile_selected_paths(_prepared(), _selection(["C1", "C2"]))
    assert [q["candidate_id"] for q in queries] == ["C1", "C2"]
    assert all(q["sparql"].startswith("SELECT DISTINCT ?value") for q in queries)
    assert "hasPLCEndPoint" not in queries[0]["sparql"]
    assert "hasEndPoint" not in queries[1]["sparql"]


@pytest.mark.parametrize("status", ["ambiguous", "unresolved"])
def test_uncertain_selection_compiles_nothing(status):
    assert compile_selected_paths(_prepared(), _selection([], status)) == []


def test_unknown_id_rejected():
    with pytest.raises(SelectionContractError, match="Unknown candidate ID"):
        compile_selected_paths(_prepared(), _selection(["C99"]))


def test_reversed_edge_rejected():
    prepared = _prepared()
    prepared["registry"]["C1"]["edges"][0]["from"] = DEVICE
    with pytest.raises(ValueError, match="disconnected or reversed"):
        compile_selected_paths(prepared, _selection(["C1"]))


def test_wrong_property_owner_rejected():
    prepared = _prepared()
    prepared["registry"]["C1"]["property"]["owner"] = DEVICE
    with pytest.raises(ValueError, match="owner"):
        compile_selected_paths(prepared, _selection(["C1"]))


def test_unsafe_predicate_iri_rejected():
    prepared = _prepared()
    prepared["registry"]["C1"]["property"]["predicate"] = "https://example.org/x> } DELETE {"
    with pytest.raises(ValueError, match="Invalid IRI"):
        compile_selected_paths(prepared, _selection(["C1"]))
