"""Compare FR/NIR/DSR on the existing IC09D identifier workload."""
import sys
import json
from collections import Counter
from itertools import product
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from selira.formal.reference_evaluator import evaluate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from compare_reassessment import compare_graph
from test_ic10_ported_manager import fixture, D, E


def run_identifier(number, domain):
    m, _, _ = fixture()
    contracts = {k: v for k, v in m._contracts.items()
                 if v[0]["id"] == "SC_" + number}
    key = next(iter(contracts))
    source = (ROOT / "contracts" / f"SC-{number}.safsl").read_text()
    bindings = json.loads((ROOT / "bindings" / f"SC-{number}.json").read_text())
    node = URIRef("urn:bounded:node")
    control = URIRef("urn:bounded:control")
    states = []
    for local, asset in product(
            [(), ("FI_101",), ("SC_101",), ("FI_101", "FI101")],
            [(), ("FI101",), ("M1",), ("FI101", "M1")]):
        g = Graph()
        for v in local:
            g.add((node, domain.hasLocalId, Literal(v)))
        for v in asset:
            g.add((node, domain.hasAssetIdentifier,
                   URIRef("https://aas.example.com/" + v)))
        g.add((control, domain.hasLocalId, Literal("CV-1006")))
        g.add((control, domain.hasAssetIdentifier,
               URIRef("https://aas.example.com/CV1006")))
        states.append(g)

    def oracle(graph):
        rows = evaluate(source, bindings, graph)["SC_" + number]
        return {(key, str(n)): "V" if row["conforms"] else "F"
                for n, row in rows.items()}

    reuse = dict(coverage_attested=True, policy_unchanged=True,
                 authority_unchanged=True)
    totals = Counter()
    disagreements = []
    for old, new in product(states, repeat=2):
        r = compare_graph(old, new, contracts, oracle, **reuse)
        totals["comparisons"] += 1
        for k in ("full_evaluations", "dsr_evaluations", "nir_evaluations",
                  "dsr_equivalent", "nir_equivalent"):
            totals[k] += r[k]
        disagreements.extend(r["disagreements"])
    assert totals["comparisons"] == totals["dsr_equivalent"] == 256
    assert totals["full_evaluations"] == 496
    assert totals["dsr_evaluations"] == 228
    for flag in reuse:
        r = compare_graph(states[-1], states[-1], contracts, oracle,
                          **dict(reuse, **{flag: False}))
        assert r["nir_equivalent"] and r["dsr_equivalent"]
        assert r["nir_evaluations"] == r["full_evaluations"] == 2
    return dict(contract="SC_" + number, snapshots=len(states), **totals,
                disagreements=disagreements, fallback_checks=3)


def test_identifier_comparison():
    results = [run_identifier("02", D), run_identifier("03", E)]
    print(json.dumps(results, indent=2))
    for r in results:
        assert r["nir_equivalent"] == r["comparisons"]
        assert r["nir_evaluations"] == r["dsr_evaluations"]
