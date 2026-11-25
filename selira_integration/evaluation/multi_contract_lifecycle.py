"""Controlled multi-contract lifecycle over the TEP RDF union.

All changes are in memory. Attestations are experimental inputs, not
independent evidence of engineering authority.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from importlib.metadata import version

from rdflib import Graph, RDF, URIRef, Literal
from process_sim.selira.multi_contract_manager import MultiContractAutomationManager

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "selira_integration/contracts"
DOMAINS = ("assetinventory", "productcatalog", "dexpi", "opcuaconnectivity", "engineeringbom")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "selira_integration/evaluation/results/multi_contract_lifecycle.json")
    args = parser.parse_args()
    manager = MultiContractAutomationManager.from_directory(CONTRACTS)
    entries = {c["id"]: c for c, _ in manager._contracts.values()}
    assert set(entries) == {"SC_01", "SC_02", "SC_03", "SC_04"}
    evidence = {t for c in entries.values() for t in c["requires_complete"]}
    graph = Graph()
    hashes = {}
    paths = [ROOT / "semantic/ontology2" / (d + "-instance.ttl") for d in DOMAINS]
    for path in paths:
        graph.parse(path, format="turtle")
    for path in paths + sorted((CONTRACTS / "safsl").glob("SC-*.safsl")) + sorted((CONTRACTS / "bindings").glob("SC-*.json")):
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    events = []

    def run(event, description, expected, mutate=None, *, initial=False,
            complete=True, coverage=True, failures=(), affected=None):
        before, rev = manager.store.snapshot()
        candidate = Graph()
        candidate += graph if initial else before
        if mutate:
            mutate(candidate)
        result = manager.submit(candidate, expected_version=rev,
                                evidence_complete=evidence if complete else (),
                                identity_normalized=True, applicability_confirmed=True,
                                coverage_attested=coverage, policy_unchanged=True,
                                authority_unchanged=True)
        after, new_rev = manager.store.snapshot()
        assert result["verdict"] == expected, (event, result)
        assert result["committed"] == (expected == "V"), event
        assert new_rev == rev + int(expected == "V"), event
        assert set(after) == set(candidate if expected == "V" else before), event
        assert {r["id"] for r in result["contracts"].values() if r["verdict"] == "F"} == set(failures), event
        report = result["reassessment"]
        if report is not None:
            assert report["equivalent"], event
            assert report["full_fallback"] == (not coverage), event
        if affected is not None:
            assert report is not None, event
            assert report["selective_evaluations"] == affected, event
        events.append(dict(result, event=event, description=description,
                           additions=len(set(candidate)-set(before)),
                           removals=len(set(before)-set(candidate))))
        print(event, expected, "version", new_rev,
              "selective/full", "-" if report is None else
              f'{report["selective_evaluations"]}/{report["full_evaluations"]}')

    def predicates(sc):
        c = entries[sc]
        return tuple(URIRef(c[k]) for k in ("focus_predicate", "catalog_predicate", "catalog_class"))

    def fresh(value):
        return URIRef("urn:selira:lifecycle:" + value)

    def reassign(g, sc, invalid=False):
        fp, tp, tc = predicates(sc)
        node = sorted(set(g.subjects(fp, None)), key=str)[0]
        old = next(g.objects(node, fp))
        values = sorted({v for t in g.subjects(RDF.type, tc) for v in g.objects(t, tp)
                         if str(v) != str(old)}, key=str)
        g.set((node, fp, Literal(str(fresh("missing"))) if invalid else values[0]))

    def duplicate(g, sc, other):
        fp, tp, tc = predicates(sc)
        other_fp, _, _ = predicates(other)
        shared = {str(v) for v in g.objects(None, fp)} & {str(v) for v in g.objects(None, other_fp)}
        assert shared
        value = sorted(shared)[0]
        g.add((fresh("duplicate-" + sc), RDF.type, tc))
        g.add((fresh("duplicate-" + sc), tp, Literal(value)))

    def unused(g):
        _, tp, tc = predicates("SC_01")
        g.add((fresh("unused-product"), RDF.type, tc))
        g.add((fresh("unused-product"), tp, Literal(str(fresh("unused-id")))))

    run("E0", "Initial admission", "V", initial=True)
    assert {r["id"]: r["focus_count"] for r in events[0]["contracts"].values()} == {
        "SC_01": 38, "SC_02": 39, "SC_03": 34, "SC_04": 71}
    run("E1", "Unreferenced product addition", "V", unused, affected=0)
    run("E2", "Structurally valid asset product reassignment", "V", lambda g: reassign(g, "SC_01"), affected=1)
    run("E3", "Unresolved asset product reference", "F", lambda g: reassign(g, "SC_01", True), failures=("SC_01",), affected=1)
    run("E4", "Duplicate product identifier shared across contracts", "F", lambda g: duplicate(g, "SC_01", "SC_04"), failures=("SC_01", "SC_04"))
    run("E5", "Duplicate asset identifier shared across contracts", "F", lambda g: duplicate(g, "SC_02", "SC_03"), failures=("SC_02", "SC_03"))
    run("E6", "Structurally valid DEXPI reassignment", "V", lambda g: reassign(g, "SC_02"), affected=1)
    run("E7", "Unresolved OPC UA asset reference", "F", lambda g: reassign(g, "SC_03", True), failures=("SC_03",), affected=1)
    run("E8", "Unresolved BOM product reference", "F", lambda g: reassign(g, "SC_04", True), failures=("SC_04",), affected=1)
    run("E9", "Incomplete evidence", "U", complete=False)
    assert events[-1]["reassessment"] is None
    run("E10", "Unconfirmed dependency coverage", "V", coverage=False, affected=182)
    reports = [e["reassessment"] for e in events if e["reassessment"] is not None]
    full = sum(r["full_evaluations"] for r in reports)
    selective = sum(r["selective_evaluations"] for r in reports)
    summary = {"events": len(events), "admitted": sum(e["committed"] for e in events),
               "rejected": sum(e["verdict"] == "F" for e in events),
               "deferred": sum(e["verdict"] == "U" for e in events),
               "comparisons": len(reports), "equivalent": sum(r["equivalent"] for r in reports),
               "full_evaluations": full, "selective_evaluations": selective,
               "logical_reduction_percent": 100 * (full-selective)/full}
    payload = {"scope": "controlled structural integrity; caller attestations; logical counts only",
               "python": platform.python_version(), "rdflib": version("rdflib"),
               "pyshacl": version("pyshacl"), "input_sha256": hashes,
               "baseline_union_triples": len(graph), "summary": summary, "events": events}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Results:", args.output)


if __name__ == "__main__":
    main()
