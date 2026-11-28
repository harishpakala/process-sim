"""Configuration-level comparison-policy variation; no runtime changes."""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef, Namespace
from selira.runtime.automation_manager import MultiContractAutomationManager
from selira.formal.reference_evaluator import evaluate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts/SC-02.safsl"
D = Namespace("https://example.org/dexpi/")
NODE = URIRef("urn:variation:equipment")
BASE = "https://aas.example.com/"
CASES = [
    ("exact_suffix", "FI101", BASE + "FI101", "F", "V"),
    ("underscore", "FI_101", BASE + "FI101", "F", "V"),
    ("hyphen", "FI-101", BASE + "FI101", "F", "V"),
    ("mismatch", "FI_101", BASE + "TI105", "F", "F"),
    ("case_sensitive", "fi101", BASE + "FI101", "F", "F"),
    ("approved_pair", "SC_101", BASE + "M1", "F", "V"),
    ("lexical_control", BASE + "FI101", BASE + "FI101", "V", "F"),
]

def graph(local, asset):
    g = Graph()
    g.add((NODE, D.hasLocalId, Literal(local)))
    g.add((NODE, D.hasAssetIdentifier, URIRef(asset)))
    return g

@pytest.mark.parametrize("kind,column", [
    ("lexical_equality", 3), ("normalized_asset_identifier", 4)])
def test_architectural_variation(tmp_path, kind, column):
    bindings = json.loads((ROOT / "bindings/SC-02.json").read_text())
    template = next(iter(bindings["templates"].values()))
    if kind == "lexical_equality":
        template["comparison_policy"] = {"kind": kind}
    path = tmp_path / "SC-02.json"
    path.write_text(json.dumps(bindings), encoding="utf-8")
    def manager():
        return MultiContractAutomationManager([(SOURCE, path)])
    rows = []
    for case in CASES:
        name, local, asset = case[:3]
        expected = case[column]
        m = manager()
        entry, _ = next(iter(m._contracts.values()))
        assert entry["comparison_policy"]["kind"] == kind
        flags = dict(evidence_complete=entry["requires_complete"],
                     identity_normalized=True, applicability_confirmed=True)
        g = graph(local, asset)
        oracle = evaluate(SOURCE.read_text(), bindings, g)["SC_02"]
        assert oracle[NODE]["conforms"] == (expected == "V")
        r = m.submit(g, expected_version=0, **flags)
        assert r["verdict"] == expected, r
        assert r["committed"] == (expected == "V")
        assert next(iter(r["contracts"].values()))["equivalent"]
        assert m.store.snapshot()[1] == int(expected == "V")
        rows.append(dict(case=name, verdict=r["verdict"], committed=r["committed"]))
    m = manager()
    entry, _ = next(iter(m._contracts.values()))
    flags = dict(evidence_complete=entry["requires_complete"],
                 identity_normalized=True, applicability_confirmed=True)
    valid = graph(BASE + "FI101" if column == 3 else "FI_101", BASE + "FI101")
    assert m.submit(valid, expected_version=0, **flags)["committed"]
    reuse = dict(coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
    unchanged = m.submit(valid, expected_version=1, **flags, **reuse)
    assert unchanged["committed"]
    assert unchanged["reassessment"]["equivalent"]
    assert unchanged["reassessment"]["selective_evaluations"] == 0
    invalid = graph("different", BASE + "FI101")
    changed = m.submit(invalid, expected_version=2, **flags, **reuse)
    assert changed["verdict"] == "F" and not changed["committed"]
    assert changed["reassessment"]["equivalent"]
    assert changed["reassessment"]["selective_evaluations"] == 1
    fallback = m.submit(valid, expected_version=2, **flags,
                        **dict(reuse, policy_unchanged=False))
    assert fallback["committed"]
    assert fallback["reassessment"]["full_fallback"]
    assert fallback["reassessment"]["equivalent"]
    assert fallback["reassessment"]["selective_evaluations"] == fallback["reassessment"]["full_evaluations"] == 1
    print(json.dumps(dict(policy=kind, cases=rows, stable_reuse=0,
                          changed_reassessment=1, attested_policy_fallback=1), indent=2))
