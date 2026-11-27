"""Real RDF baseline and controlled, in-memory lifecycle for migrated contracts."""
import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from rdflib import Graph, Literal, URIRef, RDF
from selira.runtime.automation_manager import MultiContractAutomationManager
from selira.runtime.reassessment.selective import compare
from selira.formal.identifier_comparison import identifier_matches

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT
DOMAINS = ("assetinventory", "productcatalog", "dexpi", "ecad", "engineeringbom")


def run():
    manager = MultiContractAutomationManager.from_directory(CONTRACTS)
    graph = Graph()
    paths = [ROOT / "datasets/tep_nexus" / (d + "-instance.ttl") for d in DOMAINS]
    for path in paths:
        graph.parse(path, format="turtle")
    paths += sorted((CONTRACTS / "contracts").glob("*.safsl"))
    paths += sorted((ROOT / "policies").glob("*.safsl"))
    paths += sorted((CONTRACTS / "bindings").glob("SC-*.json"))
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    evidence = {t for c, _ in manager._contracts.values() for t in c["requires_complete"]}
    flags = dict(evidence_complete=evidence, identity_normalized=True, applicability_confirmed=True)
    reuse = dict(coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
    baseline = manager.submit(graph, expected_version=0, **flags)
    assert not baseline["committed"], baseline
    assert baseline["verdict"] == "F", baseline
    assert all(r["equivalent"] is True for r in baseline["contracts"].values()), baseline
    details = {}
    controlled = Graph()
    controlled += graph
    for key, (entry, _) in manager._contracts.items():
        if entry.get("kind") != "standalone_match":
            continue
        left, right = map(URIRef, (entry["left_predicate"], entry["right_predicate"]))
        exceptions = tuple(tuple(p) for p in entry["comparison_policy"].get("exceptions", []))
        rows = []
        for node in sorted(set(graph.subjects(right, None)), key=str):
            local = list(graph.objects(node, left))
            asset = list(graph.objects(node, right))
            valid = False
            if len(local) == len(asset) == 1:
                try:
                    valid = identifier_matches(str(local[0]), str(asset[0]), exceptions=exceptions)
                except ValueError:
                    pass
            rows.append(dict(node=str(node), local_ids=sorted(map(str, local)),
                             asset_identifiers=sorted(map(str, asset)), conforms=valid))
            if not valid:
                # Experimental repair only: not an engineering recommendation.
                assert len(asset) == 1
                controlled.set((node, left, Literal(str(asset[0]).rsplit("/", 1)[-1])))
        violations = {r["node"] for r in rows if not r["conforms"]}
        assert violations == set(baseline["contracts"][key]["violations"])
        details[entry["id"]] = dict(total=len(rows), consistent=len(rows)-len(violations),
                                    inconsistent=len(violations), rows=rows)
    assert {k: (v["total"], v["inconsistent"]) for k, v in details.items()} == {
        "SC_02": (39, 9), "SC_03": (40, 29)}
    repair_comparison = compare(graph, controlled, manager._contracts, **reuse)
    assert repair_comparison["equivalent"]
    assert repair_comparison["selective_evaluations"] == 38
    entries = {c['id']: c for c, _ in manager._contracts.values()}
    events = []
    def submit(name, candidate, expected, *, coverage=True, complete=True, affected=None, failures=()):
        before, rev = manager.store.snapshot()
        result = manager.submit(candidate, expected_version=rev,
                                **(flags if complete else {}),
                                **dict(reuse, coverage_attested=coverage))
        assert result["verdict"] == expected, (name, result)
        after, new_rev = manager.store.snapshot()
        assert new_rev == rev + int(expected == "V")
        assert set(after) == set(candidate if expected == "V" else before)
        assert result["committed"] == (expected == "V"), name
        assert {r["id"] for r in result["contracts"].values() if r["verdict"] == "F"} == set(failures), name
        report = result["reassessment"]
        if report is not None:
            assert report["equivalent"], result
            assert report["full_fallback"] == (not coverage), name
        if affected is not None:
            assert report is not None and report["selective_evaluations"] == affected, result
        events.append(dict(result, event=name, additions=len(set(candidate)-set(before)), removals=len(set(before)-set(candidate))))
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

    submit("controlled_initial_admission", controlled, "V")
    assert {r["id"]: r["focus_count"] for r in events[0]["contracts"].values()} == {
        "SC_01": 38, "SC_02": 39, "SC_03": 40, "SC_04": 71}
    for name, mutate, expected, affected, failures in (
        ("unreferenced_product_addition", unused, "V", 0, ()),
        ("valid_asset_product_reassignment", lambda g: reassign(g, "SC_01"), "V", 1, ()),
        ("unresolved_asset_product_reference", lambda g: reassign(g, "SC_01", True), "F", 1, ("SC_01",)),
        ("shared_duplicate_product_identifier", lambda g: duplicate(g, "SC_01", "SC_04"), "F", 6, ("SC_01", "SC_04")),
        ("unresolved_bom_product_reference", lambda g: reassign(g, "SC_04", True), "F", 1, ("SC_04",)),
    ):
        candidate, _ = manager.store.snapshot()
        mutate(candidate)
        submit(name, candidate, expected, affected=affected, failures=failures)

    for sc in ("SC_02", "SC_03"):
        entry = next(e for e, _ in manager._contracts.values() if e["id"] == sc)
        left, right = map(URIRef, (entry["left_predicate"], entry["right_predicate"]))
        node = sorted(set(controlled.subjects(right, None)), key=str)[0]
        candidate, _ = manager.store.snapshot()
        candidate.set((node, left, Literal("IC09_VALID")))
        candidate.set((node, right, URIRef("https://aas.example.com/IC09VALID")))
        submit(sc + "_valid_identifier_reassignment", candidate, "V", affected=1)
        candidate, _ = manager.store.snapshot()
        candidate.set((node, left, Literal("IC08_INVALID")))
        submit(sc + "_local_mismatch", candidate, "F", affected=1, failures=(sc,))
        candidate, _ = manager.store.snapshot()
        candidate.set((node, right, URIRef("https://aas.example.com/IC08INVALID")))
        submit(sc + "_asset_mismatch", candidate, "F", affected=1, failures=(sc,))
    candidate, _ = manager.store.snapshot()
    candidate.add((URIRef("urn:ic08:unrelated"), URIRef("https://example.org/opcuaconnectivity/hasAssetIdentifier"), Literal("unrelated")))
    submit("unrelated_opcua_change", candidate, "V", affected=0)
    submit("missing_attestations", candidate, "U", complete=False)
    submit("coverage_fallback", candidate, "V", coverage=False, affected=188)
    reports = [e["reassessment"] for e in events if e["reassessment"] is not None]
    full = sum(r["full_evaluations"] for r in reports)
    selective = sum(r["selective_evaluations"] for r in reports)
    return dict(scope="Real baseline; controlled in-memory repair and lifecycle; caller attestations; logical counts only",
                python=platform.python_version(), rdflib=version("rdflib"), pyshacl=version("pyshacl"),
                input_sha256=hashes, baseline_union_triples=len(graph), baseline=baseline,
                identifier_details=details, repair_comparison=repair_comparison, events=events,
                summary=dict(events=1+len(events), admitted=sum(e["committed"] for e in events),
                             rejected=1+sum(e["verdict"] == "F" for e in events), deferred=sum(e["verdict"] == "U" for e in events),
                             full_evaluations=full, selective_evaluations=selective,
                             equivalent_comparisons=sum(r["equivalent"] for r in reports),
                             comparisons=len(reports), logical_reduction_percent=100*(full-selective)/full))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/reproduced/multi_contract_lifecycle.json")
    args = parser.parse_args()
    payload = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": payload["baseline"]["verdict"], "summary": payload["summary"]}, indent=2))
    print("Results:", args.output)


if __name__ == "__main__":
    main()
