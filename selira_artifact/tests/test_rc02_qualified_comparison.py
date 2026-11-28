"""RC02 comparison on the existing IC14 qualified workload."""
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from rdflib import Graph, Literal
from test_ic10_ported_manager import fixture, N, P, D
from selira.runtime.reassessment.selective import project, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))
from compare_reassessment import select_naive


@pytest.mark.parametrize("coverage", [True, False], ids=["covered", "fallback"])
def test_rc02_qualified_comparison(coverage):
    manager, base, flags = fixture()
    contracts = manager._contracts
    snapshots = []
    for graph_case, evidence_case in itertools.product(
            ("valid", "reference", "identifier", "unrelated"),
            ("complete", "incomplete", "identity", "applicability")):
        graph = Graph()
        graph += base
        if graph_case == "reference":
            graph.set((N.product, P.hasProductIdentifier, Literal("other")))
        elif graph_case == "identifier":
            graph.set((N.equipment, D.hasLocalId, Literal("TI_105")))
        elif graph_case == "unrelated":
            graph.add((N.other, P.note, Literal("unrelated")))
        evidence = set(flags["evidence_complete"])
        if evidence_case == "incomplete":
            evidence.clear()
        identity = evidence_case != "identity"
        applicability = evidence_case != "applicability"
        context = (frozenset(evidence), identity, applicability)
        full = {key: manager._evaluate(graph, entry, ttl, evidence,
                                       identity, applicability)["verdict"]
                for key, (entry, ttl) in contracts.items()}
        assert set(full.values()) <= {"V", "F", "U"}
        if evidence_case != "complete":
            assert set(full.values()) == {"U"}
        else:
            assert ("F" in full.values()) == (
                graph_case in {"reference", "identifier"})
        snapshots.append((graph, context, project(graph, contracts), full))

    totals = Counter(dict(comparisons=0, full_evaluations=0,
                          dsr_evaluations=0, nir_evaluations=0,
                          dsr_equivalent=0, nir_equivalent=0,
                          fallback_comparisons=0, self_comparisons=0,
                          covered_nonself_comparisons=0))
    disagreements = Counter()
    for before, after in itertools.product(snapshots, repeat=2):
        old_graph, old_context, (old, oi), prior = before
        graph, context, (new, ni), full = after
        affected, fallback = select(
            old, oi, new, ni, coverage_attested=coverage,
            policy_unchanged=True, authority_unchanged=old_context == context,
            policy_executor=manager._policy_executor)
        assert fallback == (not coverage or old_context != context)
        dsr_keys = set(contracts) if fallback else {k for k, _ in affected}
        nir_keys = set(contracts) if fallback else {
            k for k, _ in select_naive(old_graph, graph, old, new,
                                       full_fallback=False)}
        evidence, identity, applicability = context
        dsr = dict(prior)
        for key in dsr_keys:
            entry, ttl = contracts[key]
            dsr[key] = manager._evaluate(
                graph, entry, ttl, set(evidence), identity, applicability)["verdict"]
        # Oracle-based logical reuse: no incremental execution-time claim.
        nir = {k: full[k] if k in nir_keys else prior[k] for k in contracts}
        assert dsr == full
        if fallback:
            assert nir == full and nir_keys == dsr_keys == set(contracts)
        for k in contracts:
            if nir[k] != full[k]:
                disagreements[(full[k], nir[k])] += 1
        totals["comparisons"] += 1
        totals["full_evaluations"] += len(contracts)
        totals["dsr_evaluations"] += len(dsr_keys)
        totals["nir_evaluations"] += len(nir_keys)
        totals["dsr_equivalent"] += dsr == full
        totals["nir_equivalent"] += nir == full
        totals["fallback_comparisons"] += fallback
        totals["self_comparisons"] += before is after
        totals["covered_nonself_comparisons"] += not fallback and before is not after

    assert totals["comparisons"] == totals["dsr_equivalent"] == 256
    assert totals["full_evaluations"] == 1024
    assert totals["fallback_comparisons"] == (192 if coverage else 256)
    assert totals["self_comparisons"] == 16
    assert totals["covered_nonself_comparisons"] == (48 if coverage else 0)
    if coverage:
        assert 0 < totals["dsr_evaluations"] < 1024
    else:
        assert totals["dsr_evaluations"] == totals["nir_evaluations"] == 1024
    print(json.dumps(dict(coverage=coverage, snapshots=len(snapshots), **totals,
                          disagreements=[
                              dict(full=f, naive=n, count=c)
                              for (f, n), c in sorted(disagreements.items())],
                          scope="Logical contract-level evaluations; shared fallback"),
                     indent=2))
