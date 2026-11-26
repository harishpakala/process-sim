"""Unified TEP NEXUS evaluation; original RDF files are never modified."""
import json
from time import perf_counter
from selira.runtime.selective_manager import SelectiveAutomationManager
import argparse
from pathlib import Path
from rdflib import Graph, RDF, URIRef, Literal
from rdflib.namespace import SH
from pyshacl import validate
from selira.formal.reference_evaluator import evaluate
from selira.compiler.shacl import compile_contract
from selira.runtime.automation_manager import MultiContractAutomationManager
from characterize_tep_nexus import characterize, DOMAINS

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=ROOT.parent / "semantic/ontology2")
    p.add_argument("--output", type=Path, default=ROOT / "evaluation/results/reproduced/selective_tep.json")
    args = p.parse_args()
    baseline = Graph()
    for domain in DOMAINS:
        baseline.parse(args.dataset / (domain + "-instance.ttl"), format="turtle")
    characterization = characterize(args.dataset, ROOT / "bindings")
    artifacts = []
    for path in sorted((ROOT / "contracts").glob("SC-*.safsl")):
        source = path.read_text(encoding="utf-8")
        binding = json.loads((ROOT / "bindings" / (path.stem + ".json")).read_text(encoding="utf-8"))
        ttl, manifest = compile_contract(source, binding)
        artifacts.append((path.stem, source, binding, ttl, manifest["contracts"][0]))
    manager = MultiContractAutomationManager.from_directory(ROOT)
    selective_manager = SelectiveAutomationManager.from_directory(ROOT)
    evidence = {t for _, _, _, _, m in artifacts for t in m["requires_complete"]}
    events = []
    def run(name, candidate, expected, violations, affected=None, **flags):
        before, rev = manager.store.snapshot()
        structural = {}
        for key, source, binding, ttl, m in artifacts:
            rows = evaluate(source, binding, candidate)[m["id"]]
            expected_nodes = {n for n, r in rows.items() if r["cardinality"] != 1}
            conforms, report, _ = validate(candidate, shacl_graph=Graph().parse(data=ttl, format="turtle"), inference="none")
            actual = {str(n) for n in report.objects(None, SH.focusNode)}
            assert actual == expected_nodes == set(violations.get(key, [])), (name, key, actual, expected_nodes)
            assert bool(conforms) == (not expected_nodes)
            structural[key] = {"instances": len(rows), "violations": sorted(actual), "equivalent": True}
        options = dict(expected_version=rev, evidence_complete=evidence, identity_normalized=True,
                       applicability_confirmed=True, coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
        options.update(flags)
        started = perf_counter()
        result = manager.submit(candidate, **options)
        full_seconds = perf_counter() - started
        selective_result = selective_manager.submit(candidate, **options)
        assert selective_result["verdict"] == result["verdict"], (name, selective_result, result)
        assert selective_result["version"] == result["version"]
        assert selective_result["committed"] == result["committed"]
        for key, outcome in result["contracts"].items():
            other = selective_result["contracts"][key]
            assert outcome["verdict"] == other["verdict"]
            assert outcome.get("violations", []) == other.get("violations", [])
        assert set(selective_manager.store.snapshot()[0]) == set(manager.store.snapshot()[0])
        if affected is not None:
            assert selective_result["executed_instances"] == affected, (name, selective_result)
        after, new_rev = manager.store.snapshot()
        assert result["verdict"] == expected, (name, result)
        assert result["committed"] == (expected == "V")
        assert new_rev == rev + int(expected == "V")
        assert set(after) == set(candidate if expected == "V" else before)
        reassess = result["reassessment"]
        if affected is not None:
            assert reassess and reassess["equivalent"] and reassess["selective_evaluations"] == affected, (name, reassess)
        events.append({"scenario": name, "structural": structural, "admission": result, "selective_admission": selective_result, "full_seconds": full_seconds})
        print(name, expected, "affected", None if reassess is None else reassess["selective_evaluations"], flush=True)
    def copy():
        return Graph() + baseline
    run("baseline", copy(), "V", {})
    # Each target identifier is an actual dataset dependency, including unused targets.
    groups = {}
    for d in characterization["identifier_dependencies"]:
        groups.setdefault(d["target_class"], []).append(d)
    for tc, ds in sorted(groups.items()):
        # Deterministic minimum and maximum impact, plus a shared identifier.
        ordered = sorted(ds, key=lambda d: (d["reference_count"], d["identifier"]))
        selected = {d["identifier"]: d for d in (ordered[0], ordered[-1])}
        shared = [d for d in ordered if d["shared_across_contracts"]]
        if shared:
            selected[shared[0]["identifier"]] = shared[0]
        for i, d in enumerate(selected.values()):
            g = copy()
            pred = URIRef(d["target_predicate"])
            target_class = URIRef(tc)
            node = URIRef("urn:selira:evaluation:duplicate")
            g.add((node, RDF.type, target_class))
            g.add((node, pred, Literal(d["identifier"])))
            violations = {}
            for r in d["references"]:
                violations.setdefault(r["contract"], []).append(r["resource"])
            n = d["reference_count"]
            run("duplicate:" + d["identifier"], g, "F" if n else "V", violations, n)
            # Restore the baseline after an admitted unused duplicate.
            if not n:
                run("restore:" + d["identifier"], copy(), "V", {}, 0)
            else:
                g = copy()
                for target in list(g.subjects(RDF.type, target_class)):
                    if any(str(v) == d["identifier"] for v in g.objects(target, pred)):
                        g.remove((target, RDF.type, target_class))
                run("remove:" + d["identifier"], g, "F", violations, n)
    for name, flags in [
        ("incomplete", {"evidence_complete": ()}),
        ("identity_unconfirmed", {"identity_normalized": False}),
        ("applicability_unconfirmed", {"applicability_confirmed": False}),
        ("stale", {"expected_version": -1})]:
        run(name, copy(), "U", {}, **flags)
    for flag in ("coverage_attested", "policy_unchanged", "authority_unchanged"):
        run("fallback:" + flag, copy(), "V", {}, characterization["total_focus"], **{flag: False})
    reports = [e["admission"]["reassessment"] for e in events if e["admission"]["reassessment"] is not None]
    full = sum(r["full_evaluations"] for r in reports)
    selective = sum(r["selective_evaluations"] for r in reports)
    summary = {"scenarios": len(events), "structural_comparisons": sum(len(e["structural"]) for e in events),
               "admitted": sum(e["admission"]["committed"] for e in events),
               "rejected": sum(e["admission"]["verdict"] == "F" for e in events),
               "deferred": sum(e["admission"]["verdict"] == "U" for e in events),
               "reassessment_comparisons": len(reports), "full": full, "selective": selective,
               "logical_reduction_percent": 100 * (full-selective)/full}
    summary.update(executed_instances=sum(e["selective_admission"]["executed_instances"] for e in events),
                   reused_instances=sum(e["selective_admission"]["reused_instances"] for e in events),
                   selective_shacl_calls=sum(e["selective_admission"]["shacl_calls"] for e in events),
                   full_seconds=sum(e["full_seconds"] for e in events),
                   selective_seconds=sum(e["selective_admission"]["elapsed_seconds"] for e in events))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"characterization": characterization, "summary": summary, "events": events}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
