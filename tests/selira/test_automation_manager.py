"""Regression tests for the local SC-01 Automation Manager."""
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, RDF, Literal, URIRef

from process_sim.selira.automation_manager import AutomationManager

ROOT = Path(__file__).resolve().parents[2]
AI = Namespace("https://example.org/assetinventory/")
PC = Namespace("https://example.org/productcatalog/")
A = URIRef("urn:test:asset")
P = URIRef("urn:test:product")


@pytest.fixture
def setup():
    contracts = ROOT / "selira_integration/contracts"
    manager = AutomationManager(contracts / "safsl/SC-01.safsl",
                                contracts / "bindings/SC-01.json")
    graph = Graph()
    graph.add((A, RDF.type, AI.Asset))
    graph.add((A, AI.hasProductIdentifier, Literal("p")))
    graph.add((P, RDF.type, PC.Product))
    graph.add((P, PC.hasProductIdentifier, Literal("p")))
    return manager, graph


def submit(manager, graph, version=0, **overrides):
    options = dict(expected_version=version,
                   evidence_complete=manager.contract["requires_complete"],
                   identity_normalized=True, applicability_confirmed=True,
                   coverage_attested=True, policy_unchanged=True,
                   authority_unchanged=True)
    options.update(overrides)
    return manager.submit(graph, **options)


def test_initial_admission(setup):
    manager, graph = setup
    result = submit(manager, graph)
    assert result["verdict"] == "V"
    assert result["committed"]
    assert result["reassessment"] is None
    stored, version = manager.store.snapshot()
    assert version == 1 and set(stored) == set(graph)


@pytest.mark.parametrize("case,verdict", [
    ("missing", "F"), ("duplicate", "F"), ("incomplete", "U"),
    ("identity", "U"), ("applicability", "U"), ("stale", "U"),
    ("empty", "NA"), ("nonasset", "U"), ("multivalued", "U"),
])
def test_nonadmission_preserves_snapshot(setup, case, verdict):
    manager, graph = setup
    assert submit(manager, graph)["committed"]
    candidate = Graph()
    candidate += graph
    options = {}
    version = 1
    if case == "missing":
        candidate.set((A, AI.hasProductIdentifier, Literal("missing")))
    elif case == "duplicate":
        q = URIRef("urn:test:duplicate")
        candidate.add((q, RDF.type, PC.Product))
        candidate.add((q, PC.hasProductIdentifier, Literal("p")))
    elif case == "incomplete":
        options["evidence_complete"] = []
    elif case == "identity":
        options["identity_normalized"] = False
    elif case == "applicability":
        options["applicability_confirmed"] = False
    elif case == "stale":
        version = 0
    elif case == "empty":
        candidate.remove((A, AI.hasProductIdentifier, None))
    elif case == "nonasset":
        candidate.remove((A, RDF.type, AI.Asset))
    elif case == "multivalued":
        candidate.add((A, AI.hasProductIdentifier, Literal("other")))
    result = submit(manager, candidate, version, **options)
    assert result["verdict"] == verdict
    assert not result["committed"]
    stored, actual_version = manager.store.snapshot()
    assert actual_version == 1 and set(stored) == set(graph)
    assert len(manager.history) == 2


@pytest.mark.parametrize("coverage,expected", [(True, 0), (False, 1)])
def test_selectivity_and_fallback(setup, coverage, expected):
    manager, graph = setup
    assert submit(manager, graph)["committed"]
    q = URIRef("urn:test:unused")
    graph.add((q, RDF.type, PC.Product))
    graph.add((q, PC.hasProductIdentifier, Literal("unused")))
    result = submit(manager, graph, 1, coverage_attested=coverage)
    assert result["committed"] and result["version"] == 2
    report = result["reassessment"]
    assert report["equivalent"]
    assert report["full_evaluations"] == 1
    assert report["selective_evaluations"] == expected
    assert report["full_fallback"] == (not coverage)
