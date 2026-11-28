"""Evidence-only qualification experiments; no incremental SHACL claim."""
import pytest
from rdflib import Graph, Literal
from pyshacl import validate

from test_ic10_ported_manager import fixture, N, P


@pytest.mark.parametrize("invalid", [False, True], ids=["conforming", "nonconforming"])
@pytest.mark.parametrize("withdrawal", ["completeness", "identity", "applicability"])
def test_evidence_only_transitions(invalid, withdrawal):
    manager, graph, flags = fixture()
    if invalid:
        graph.set((N.product, P.hasProductIdentifier, Literal("other")))
    original = set(graph)
    expected = "F" if invalid else "V"
    expected_contracts = {
        entry["id"]: ("F" if invalid and entry["id"] in {"SC_01", "SC_04"} else "V")
        for entry, _ in manager._contracts.values()
    }
    assert len(expected_contracts) == 4
    reduced = dict(flags)
    if withdrawal == "completeness":
        reduced["evidence_complete"] = set()
    elif withdrawal == "identity":
        reduced["identity_normalized"] = False
    else:
        reduced["applicability_confirmed"] = False

    # Independently check graph conformance, even when qualification
    # deliberately avoids SHACL execution due to missing attestations.
    for entry, ttl in manager._contracts.values():
        conforms, _, _ = validate(
            graph, shacl_graph=Graph().parse(data=ttl, format="turtle"),
            inference="none", advanced=False, abort_on_first=False)
        assert bool(conforms) == (expected_contracts[entry["id"]] == "V")

    for label, evidence, verdict in (
        ("initial", flags, expected),
        ("withdrawn", reduced, "U"),
        ("restored", flags, expected),
    ):
        before, version = manager.store.snapshot()
        before_triples = set(before)
        result = manager.submit(
            graph, expected_version=version, **evidence,
            coverage_attested=False, policy_unchanged=True,
            authority_unchanged=False)
        assert result["verdict"] == verdict
        assert result["committed"] == (verdict == "V")
        assert {r["id"]: r["verdict"] for r in result["contracts"].values()} == (
            {key: "U" for key in expected_contracts}
            if verdict == "U" else expected_contracts)
        after, new_version = manager.store.snapshot()
        assert new_version == version + int(verdict == "V")
        assert set(after) == (original if verdict == "V" else before_triples)
        assert set(graph) == original
        if verdict == "U":
            assert result["reassessment"] is None
        if result["reassessment"] is not None:
            assert result["reassessment"]["full_fallback"]
            assert result["reassessment"]["equivalent"]
            assert result["reassessment"]["selective_evaluations"] == 4
        print(f"{invalid=}, {withdrawal=}, {label=}, {verdict=}, "
              f"committed={result['committed']}, version={new_version}")
