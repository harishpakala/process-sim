"""Offline tests for one-request engineering/signal resolution."""
import pytest

from process_sim.api.unified_graph_resolution_experimental import (
    compile_entity_signal_query, resolve_entity_signal,
)

EVIDENCE = {"properties": [{"property": "hasLocalId"}, {"property": "hasAssetIdentifier"}]}


def test_dexpi_compiler_uses_one_select_and_named_graphs():
    query = compile_entity_signal_query("DEXPI", "FI_101", evidence=EVIDENCE)
    assert query.count("SELECT ") == 1
    assert "GRAPH ?engineeringGraph" in query
    assert "GRAPH ?mappingGraph" in query
    assert "eng:InstrumentationFunction" in query
    assert 'FILTER(STR(?localId) = "FI_101")' in query


def test_ecad_compiler_does_not_assume_dexpi_class():
    query = compile_entity_signal_query("ECAD", "FI-101", evidence=EVIDENCE)
    assert "eng:InstrumentationFunction" not in query
    assert "https://example.org/ecad/" in query


def test_resolution_one_call_unique_identity_and_signal():
    calls = []
    def executor(endpoint, sparql):
        calls.append((endpoint, sparql))
        return [{"entity": "urn:entity:1", "assetIdentifier": "asset-1",
                 "signalName": "signal-1"}]
    result = resolve_entity_signal(
        "http://example.invalid/sparql", "DEXPI", "FI_101",
        evidence=EVIDENCE, executor=executor)
    assert len(calls) == 1
    assert result["entity"] == "urn:entity:1"
    assert result["operational_signal"] == "signal-1"


def test_resolution_rejects_ambiguous_mapping():
    def executor(endpoint, sparql):
        return [{"entity": "urn:entity:1", "assetIdentifier": "asset-1",
                 "signalName": name} for name in ("a", "b")]
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_entity_signal("http://example.invalid", "DEXPI", "FI_101",
                              evidence=EVIDENCE, executor=executor)


def test_resolution_rejects_missing_shacl_evidence_and_invalid_id_before_io():
    with pytest.raises(ValueError, match="SHACL"):
        compile_entity_signal_query("DEXPI", "FI_101", evidence={})
    with pytest.raises(ValueError, match="LocalId"):
        compile_entity_signal_query("DEXPI", 'FI_101" } UNION {', evidence=EVIDENCE)
