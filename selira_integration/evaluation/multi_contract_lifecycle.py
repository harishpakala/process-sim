"""Real RDF baseline and controlled, in-memory lifecycle for migrated contracts."""
import argparse
import hashlib
import json
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from process_sim.selira.multi_contract_manager import MultiContractAutomationManager
from process_sim.selira.reassessment.multi_contract import compare
from process_sim.safsl.shacl.identifier_comparison import identifier_matches

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "selira_integration/contracts"
DOMAINS = ("assetinventory", "productcatalog", "dexpi", "ecad", "engineeringbom")


def run():
    manager = MultiContractAutomationManager.from_directory(CONTRACTS)
    graph = Graph()
    paths = [ROOT / "semantic/ontology2" / (d + "-instance.ttl") for d in DOMAINS]
    for path in paths:
        graph.parse(path, format="turtle")
    paths += sorted((CONTRACTS / "safsl").glob("*.safsl"))
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
    events = []
    def submit(name, candidate, expected, *, coverage=True, complete=True, affected=None):
        before, rev = manager.store.snapshot()
        result = manager.submit(candidate, expected_version=rev,
                                **(flags if complete else {}),
                                **dict(reuse, coverage_attested=coverage))
        assert result["verdict"] == expected, (name, result)
        after, new_rev = manager.store.snapshot()
        assert new_rev == rev + int(expected == "V")
        assert set(after) == set(candidate if expected == "V" else before)
        report = result["reassessment"]
        if report is not None:
            assert report["equivalent"], result
        if affected is not None:
            assert report is not None and report["selective_evaluations"] == affected, result
        events.append(dict(result, event=name))
    submit("controlled_initial_admission", controlled, "V")
    for sc in ("SC_02", "SC_03"):
        entry = next(e for e, _ in manager._contracts.values() if e["id"] == sc)
        left, right = map(URIRef, (entry["left_predicate"], entry["right_predicate"]))
        node = sorted(set(controlled.subjects(right, None)), key=str)[0]
        candidate, _ = manager.store.snapshot()
        candidate.set((node, left, Literal("IC08_INVALID")))
        submit(sc + "_local_mismatch", candidate, "F", affected=1)
        candidate, _ = manager.store.snapshot()
        candidate.set((node, right, URIRef("https://aas.example.com/IC08INVALID")))
        submit(sc + "_asset_mismatch", candidate, "F", affected=1)
    candidate, _ = manager.store.snapshot()
    candidate.add((URIRef("urn:ic08:unrelated"), URIRef("https://example.org/opcuaconnectivity/hasAssetIdentifier"), Literal("unrelated")))
    submit("unrelated_opcua_change", candidate, "V", affected=0)
    submit("missing_attestations", candidate, "U", complete=False)
    submit("coverage_fallback", candidate, "V", coverage=False)
    reports = [e["reassessment"] for e in events if e["reassessment"] is not None]
    full = sum(r["full_evaluations"] for r in reports)
    selective = sum(r["selective_evaluations"] for r in reports)
    return dict(scope="Real baseline; controlled in-memory repair and lifecycle; caller attestations; logical counts only",
                input_sha256=hashes, baseline_union_triples=len(graph), baseline=baseline,
                identifier_details=details, repair_comparison=repair_comparison, events=events,
                summary=dict(full_evaluations=full, selective_evaluations=selective,
                             equivalent_comparisons=sum(r["equivalent"] for r in reports),
                             comparisons=len(reports), logical_reduction_percent=100*(full-selective)/full))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "selira_integration/evaluation/results/multi_contract_lifecycle_ic08.json")
    args = parser.parse_args()
    payload = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": payload["baseline"]["verdict"], "summary": payload["summary"]}, indent=2))
    print("Results:", args.output)


if __name__ == "__main__":
    main()
