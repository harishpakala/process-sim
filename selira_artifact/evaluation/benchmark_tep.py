"""Controlled paired benchmark. Correctness assertions outside manager timing."""
import argparse
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from statistics import median
from rdflib import Graph, RDF, URIRef, Literal
from selira.runtime.selective_manager import SelectiveAutomationManager
from selira.formal.reference_evaluator import evaluate
from characterize_tep_nexus import characterize, DOMAINS

ROOT = Path(__file__).resolve().parents[1]

def scenarios(baseline, characterization, evidence):
    cases = []
    def add(name, candidate, expected, violations, affected=None, **flags):
        cases.append((name, candidate, expected, violations, affected, flags))
    def copy():
        return Graph() + baseline
    add("baseline", copy(), "V", {})
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
            add("duplicate:" + d["identifier"], g, "F" if n else "V", violations, n)
            # Restore the baseline after an admitted unused duplicate.
            if not n:
                add("restore:" + d["identifier"], copy(), "V", {}, 0)
            else:
                g = copy()
                for target in list(g.subjects(RDF.type, target_class)):
                    if any(str(v) == d["identifier"] for v in g.objects(target, pred)):
                        g.remove((target, RDF.type, target_class))
                add("remove:" + d["identifier"], g, "F", violations, n)
    for name, flags in [
        ("incomplete", {"evidence_complete": ()}),
        ("identity_unconfirmed", {"identity_normalized": False}),
        ("applicability_unconfirmed", {"applicability_confirmed": False}),
        ("stale", {"expected_version": -1})]:
        add(name, copy(), "U", {}, **flags)
    for flag in ("coverage_attested", "policy_unchanged", "authority_unchanged"):
        add("fallback:" + flag, copy(), "V", {}, characterization["total_focus"], **{flag: False})

    c = characterization["contracts"]["SC-01"]
    fp = URIRef(c["source_predicate"])
    source = URIRef(c["sources"][0]["resource"])
    old = next(baseline.objects(source, fp))
    valid = next(v for t in c["targets"] for v in t["identifiers"] if v != str(old))
    g = copy()
    g.set((source, fp, Literal(valid)))
    add("reassign_valid", g, "V", {}, 1)
    bad = Graph() + g
    bad.set((source, fp, Literal("urn:selira:missing")))
    add("reassign_unresolved", bad, "F", {"SC-01": [str(source)]}, 1)
    add("recover_after_rejection", g, "V", {}, 0)
    fresh = URIRef(c["metadata_class_without_reference"][0])
    expanded = Graph() + g
    expanded.add((fresh, fp, Literal(valid)))
    add("newly_applicable", expanded, "V", {}, 1)
    add("removed_applicability", g, "V", {}, 0)
    unrelated = Graph() + g
    unrelated.add((URIRef("urn:selira:note"), URIRef("urn:selira:annotation"), Literal("changed")))
    add("unrelated_change", unrelated, "V", {}, 0)
    add("partial_evidence", unrelated, "U", {}, evidence_complete=sorted(evidence)[:-1])
    malformed = Graph() + unrelated
    malformed.add((source, fp, Literal("urn:selira:second")))
    add("invalid_cardinality", malformed, "U", {})
    add("missing_cache", unrelated, "V", {}, 182, reset_cache=True)
    add("outdated_cache", unrelated, "V", {}, 182, stale_cache=True)
    return cases

def verify_pair(full, selective, expected, violations, affected, flags, contract_ids):
    for result in (full, selective):
        assert result["verdict"] == expected, result
        assert result["committed"] == (expected == "V")
        if expected in {"V", "F"}:
            actual = {r["id"]: r["violations"] for r in result["contracts"].values() if r["violations"]}
            assert actual == {contract_ids[k]: sorted(v) for k,v in violations.items() if v}, actual
    for k in ("verdict", "committed", "version", "from_version"):
        assert full[k] == selective[k]
    assert {k:(v["verdict"],v.get("violations",[])) for k,v in full["contracts"].items()} == {k:(v["verdict"],v.get("violations",[])) for k,v in selective["contracts"].items()}
    if affected is not None:
        assert selective["executed_instances"] == affected, selective
    assert full["reused_instances"] == 0

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=ROOT.parent / "semantic/ontology2")
    p.add_argument("--output", type=Path, default=ROOT / "evaluation/results/reproduced/controlled_tep.json")
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--warmups", type=int, default=1)
    args = p.parse_args()
    if args.repetitions < 1 or args.warmups < 0:
        p.error("Invalid repetition counts")
    baseline = Graph()
    for domain in DOMAINS:
        baseline.parse(args.dataset / (domain + "-instance.ttl"), format="turtle")
    characterization = characterize(args.dataset, ROOT / "bindings")
    paths = [(p, ROOT / "bindings" / (p.stem + ".json")) for p in sorted((ROOT / "contracts").glob("SC-*.safsl"))]
    prototype = SelectiveAutomationManager(paths)
    evidence = {t for m,_ in prototype._contracts.values() for t in m["requires_complete"]}
    contract_ids = {}
    for source, binding in paths:
        evaluated = evaluate(source.read_text(encoding="utf-8"), json.loads(binding.read_text(encoding="utf-8")), baseline)
        contract_ids[source.stem], = evaluated.keys()
    cases = scenarios(baseline, characterization, evidence)
    # Independent AST oracle on supported, evidence-qualified structural cases.
    for name,g,expected,violations,_,flags in cases:
        if name == "invalid_cardinality":
            continue
        for source,binding in paths:
            evaluated = evaluate(source.read_text(encoding="utf-8"), json.loads(binding.read_text(encoding="utf-8")), g)
            rows, = evaluated.values()
            assert {n for n,r in rows.items() if r["cardinality"] != 1} == set(violations.get(source.stem, [])), name
    runs = []
    for rep in range(args.warmups + args.repetitions):
        managers = {s: SelectiveAutomationManager(paths, strategy=s) for s in ("full","selective")}
        events = []
        for j,(name,g,expected,violations,affected,flags) in enumerate(cases):
            before, rev = managers["full"].store.snapshot()
            options = dict(expected_version=rev, evidence_complete=evidence, identity_normalized=True,
                           applicability_confirmed=True, coverage_attested=True, policy_unchanged=True, authority_unchanged=True)
            options.update({k:v for k,v in flags.items() if k not in {"reset_cache","stale_cache"}})
            if flags.get("reset_cache"):
                managers["selective"]._cache = None
            if flags.get("stale_cache"):
                _,a,i,q = managers["selective"]._cache
                managers["selective"]._cache = (-1,a,i,q)
            order = ("full","selective") if (rep+j)%2 == 0 else ("selective","full")
            results = {s: managers[s].submit(g, **options) for s in order}
            verify_pair(results["full"], results["selective"], expected, violations, affected, flags, contract_ids)
            for m in managers.values():
                after, new_rev = m.store.snapshot()
                assert new_rev == rev + int(expected == "V")
                assert set(after) == set(g if expected == "V" else before)
            events.append({"scenario":name, "expected":expected, **results})
            print(rep, name, expected, results["selective"]["executed_instances"], flush=True)
        if rep >= args.warmups:
            runs.append(events)
    totals = {s:[sum(e[s]["elapsed_seconds"] for e in run) for run in runs] for s in managers}
    summary = {"scenarios":len(cases), "repetitions":args.repetitions,
               "median_seconds":{s:median(v) for s,v in totals.items()},
               "total_seconds_by_run":totals,
               "instances_per_run":{s:[sum(e[s]["executed_instances"] for e in run) for run in runs] for s in managers}}
    summary["speedup"] = summary["median_seconds"]["full"]/summary["median_seconds"]["selective"]
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*(p for pair in paths for p in pair), *sorted((ROOT/"policies").glob("*.safsl"))]}
    report = {"summary":summary,"environment":{"python":sys.version,"platform":platform.platform(),
              "dependencies":{p:version(p) for p in ("rdflib","pyshacl","lark")}},
              "warmups":args.warmups,"input_sha256":hashes,"characterization":characterization,"runs":runs}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))

if __name__ == "__main__":
    main()
