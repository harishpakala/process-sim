"""Run from repository root: python -m selira_integration.evaluation.sc01_lifecycle."""
import json
from pathlib import Path
from rdflib import Graph, Namespace, RDF, Literal, URIRef
from process_sim.selira.automation_manager import AutomationManager

ROOT = Path(__file__).resolve().parents[2]
AI = Namespace("https://example.org/assetinventory/")
PC = Namespace("https://example.org/productcatalog/")


def run():
    contracts = ROOT / "selira_integration/contracts"
    manager = AutomationManager(contracts / "safsl/SC-01.safsl",
                                contracts / "bindings/SC-01.json")
    graph = Graph()
    for name in ("assetinventory-instance.ttl", "productcatalog-instance.ttl"):
        graph.parse(ROOT / "semantic/ontology2" / name, format="turtle")
    records = []
    def submit(event, candidate, verdict, affected=None, complete=True, coverage=True):
        before, version = manager.store.snapshot()
        result = manager.submit(candidate, expected_version=version,
            evidence_complete=manager.contract["requires_complete"] if complete else [],
            identity_normalized=True, applicability_confirmed=True,
            coverage_attested=coverage, policy_unchanged=True, authority_unchanged=True)
        after, new_version = manager.store.snapshot()
        assert result["verdict"] == verdict, (event, result)
        assert result["committed"] == (verdict == "V")
        assert new_version == version + int(verdict == "V")
        assert set(after) == set(candidate if verdict == "V" else before)
        if affected is not None:
            assert result["reassessment"]["equivalent"], result
            assert result["reassessment"]["selective_evaluations"] == affected, result
        records.append({"event": event, **result})
    def current():
        return manager.store.snapshot()[0]
    submit("E0 initial admission", graph, "V")
    refs = dict(graph.subject_objects(AI.hasProductIdentifier))
    products = {p: next(graph.objects(p, PC.hasProductIdentifier))
                for p in graph.subjects(RDF.type, PC.Product)}
    used = {str(v) for v in refs.values()}
    unused = sorted((p for p,v in products.items() if str(v) not in used), key=str)[0]
    candidate = current()
    candidate.set((unused, PC.hasProductIdentifier, Literal("urn:selira:experiment:unused")))
    submit("E1 unreferenced catalog change", candidate, "V", 0)
    # Reassign a singleton to another singleton, preserving IFM and SAMSON fan-outs.
    from collections import Counter
    counts = Counter(map(str, refs.values()))
    singletons = sorted((a for a,v in refs.items() if counts[str(v)] == 1), key=str)
    asset, other = singletons[:2]
    candidate = current()
    candidate.set((asset, AI.hasProductIdentifier, refs[other]))
    submit("E2 valid reassignment", candidate, "V", 1)
    candidate = current()
    candidate.set((asset, AI.hasProductIdentifier, Literal("urn:selira:experiment:missing")))
    submit("E3 unresolved assignment", candidate, "F", 1)
    for event, suffix, count in (("E4 duplicate IFM", "/IFM_TA1101", 5),
                                 ("E5 duplicate SAMSON", "/SAMSON_3241_7", 11)):
        identifier = next(v for v in products.values() if str(v).endswith(suffix))
        candidate = current()
        duplicate = URIRef("urn:selira:experiment:duplicate")
        candidate.add((duplicate, RDF.type, PC.Product))
        candidate.add((duplicate, PC.hasProductIdentifier, identifier))
        submit(event, candidate, "F", count)
    submit("E6 incomplete candidate evidence", current(), "U", 38, complete=False)
    submit("E7 unconfirmed dependency coverage", current(), "V", 38, coverage=False)
    assert records[-1]["reassessment"]["full_fallback"]
    return records


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
