"""Experimental contract-level qualification reuse, not production caching."""
import itertools
import pytest
from rdflib import Graph, Literal
from test_ic10_ported_manager import fixture, N, P, D
from selira.runtime.reassessment.selective import project, select


@pytest.mark.parametrize("coverage", [True, False], ids=["covered", "fallback"])
def test_qualified_reassessment(coverage):
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
        def evaluate(key):
            entry, ttl = contracts[key]
            return manager._evaluate(graph, entry, ttl, evidence,
                                     identity, applicability)["verdict"]
        full = {key: evaluate(key) for key in contracts}
        assert set(full.values()) <= {"V", "F", "U"}
        if evidence_case != "complete":
            assert set(full.values()) == {"U"}
        else:
            assert ("F" in full.values()) == (graph_case in {"reference", "identifier"})
        snapshots.append((graph, context, project(graph, contracts), full))

    full_count = selective_count = comparisons = 0
    for before, after in itertools.product(snapshots, repeat=2):
        _, old_context, (old, oi), prior = before
        graph, context, (new, ni), full = after
        # Existing selection policy: changed evidence context disables reuse.
        affected, fallback = select(
            old, oi, new, ni, coverage_attested=coverage,
            policy_unchanged=True, authority_unchanged=old_context == context,
            policy_executor=manager._policy_executor)
        assert fallback == (not coverage or old_context != context)
        # Qualification is contract-level in the existing manager.
        # Reevaluate the whole contract if any of its instances is affected.
        keys = set(contracts) if fallback else {key for key, _ in affected}
        if fallback:
            assert keys == set(contracts)
        evidence, identity, applicability = context
        selective = dict(prior)
        for key in keys:
            entry, ttl = contracts[key]
            selective[key] = manager._evaluate(
                graph, entry, ttl, set(evidence), identity, applicability)["verdict"]
        assert selective == full
        full_count += len(contracts)
        selective_count += len(keys)
        comparisons += 1
    assert comparisons == 256
    assert full_count == 1024
    if coverage:
        assert 0 < selective_count < full_count
    else:
        assert selective_count == full_count
    print(f"{coverage=}, {comparisons=}, {full_count=}, {selective_count=}, "
          f"reduction={100*(1-selective_count/full_count):.2f}%")
