"""IC-09C/D: bounded qualification and logical reassessment."""
from itertools import product
import pytest
from rdflib import Graph, Literal, URIRef
from selira.runtime.reassessment.selective import compare
from test_ic10_ported_manager import fixture, D, E, N

@pytest.mark.parametrize("complete,identity,applicability", list(product((False, True), repeat=3)))
@pytest.mark.parametrize("kind", ["valid", "invalid", "empty"])
def test_qualification_matrix(complete, identity, applicability, kind):
    m, g, flags = fixture()
    assert m.submit(g, expected_version=0, **flags)["committed"]
    before, rev = m.store.snapshot()
    if kind == "invalid":
        g.set((N.equipment, D.hasLocalId, Literal("WRONG")))
    elif kind == "empty":
        g = Graph()
    result = m.submit(g, expected_version=rev,
                      evidence_complete=flags["evidence_complete"] if complete else (),
                      identity_normalized=identity, applicability_confirmed=applicability)
    expected = {"valid": "V", "invalid": "F", "empty": "NA"}[kind] if (
        complete and identity and applicability) else "U"
    assert result["verdict"] == expected
    assert result["committed"] == (expected == "V")
    after, new_rev = m.store.snapshot()
    assert new_rev == rev + int(expected == "V")
    assert set(after) == set(g if expected == "V" else before)

def test_mixed_false_unknown():
    m, g, flags = fixture()
    assert m.submit(g, expected_version=0, **flags)["committed"]
    before, rev = m.store.snapshot()
    g.set((N.equipment, D.hasLocalId, Literal("WRONG")))
    ecad = next(e for e, _ in m._contracts.values() if e["id"] == "SC_03")
    result = m.submit(g, expected_version=rev,
                      **dict(flags, evidence_complete=set(flags["evidence_complete"]) - set(ecad["requires_complete"])))
    assert {r["id"]: r["verdict"] for r in result["contracts"].values()} == {
        "SC_01": "V", "SC_02": "F", "SC_03": "U", "SC_04": "V"}
    assert result["verdict"] == "F" and not result["committed"]
    after, new_rev = m.store.snapshot()
    assert new_rev == rev and set(after) == set(before)

@pytest.mark.parametrize("number,domain", [("02", D), ("03", E)])
def test_bounded_identifier_transitions(number, domain):
    m, _, _ = fixture()
    contracts = {k: v for k, v in m._contracts.items() if v[0]["id"] == "SC_" + number}
    key = next(iter(contracts))
    node = URIRef("urn:bounded:node")
    control = URIRef("urn:bounded:control")
    states = []
    for local, asset in product([(), ("FI_101",), ("SC_101",), ("FI_101", "FI101")],
                                [(), ("FI101",), ("M1",), ("FI101", "M1")]):
        g = Graph()
        for v in local:
            g.add((node, domain.hasLocalId, Literal(v)))
        for v in asset:
            g.add((node, domain.hasAssetIdentifier, URIRef("https://aas.example.com/" + v)))
        g.add((control, domain.hasLocalId, Literal("CV-1006")))
        g.add((control, domain.hasAssetIdentifier, URIRef("https://aas.example.com/CV1006")))
        states.append((g, local, asset))
    full = selective = count = 0
    reuse = dict(coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
    for (old, ol, oa), (new, nl, na) in product(states, repeat=2):
        r = compare(old, new, contracts, **reuse)
        affected = bool(oa or na) and ((ol, oa) != (nl, na))
        assert r["equivalent"] and not r["full_fallback"]
        assert r["affected"] == ([[key, str(node)]] if affected else [])
        assert r["full_evaluations"] == 1 + int(bool(oa or na))
        assert r["selective_evaluations"] == int(affected)
        full += r["full_evaluations"]
        selective += r["selective_evaluations"]
        count += 1
    assert (count, full, selective) == (256, 496, 228)
    for flag in reuse:
        r = compare(states[-1][0], states[-1][0], contracts, **dict(reuse, **{flag: False}))
        assert r["equivalent"] and r["full_fallback"]
        assert r["full_evaluations"] == r["selective_evaluations"] == 2
