"""Representative paired timings, independently seeded from a verified baseline.

Each completed pair is atomically checkpointed. Resume skips completed pairs.
Baseline initialization is measured separately, not included in workload timings.
"""
import argparse
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from statistics import median
from rdflib import Graph
from benchmark_tep import ROOT, DOMAINS, characterize, scenarios, verify_pair
from selira.runtime.selective_manager import SelectiveAutomationManager
from selira.formal.reference_evaluator import evaluate

def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(path)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=ROOT.parent/"semantic/ontology2")
    p.add_argument("--output", type=Path, default=ROOT/"evaluation/results/reproduced/representative_tep.json")
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    if args.repetitions < 1:
        p.error("Positive repetition count required")
    baseline = Graph()
    for domain in DOMAINS:
        baseline.parse(args.dataset/(domain+"-instance.ttl"), format="turtle")
    characterization = characterize(args.dataset, ROOT/"bindings")
    paths = [(p,ROOT/"bindings"/(p.stem+".json")) for p in sorted((ROOT/"contracts").glob("SC-*.safsl"))]
    seed = SelectiveAutomationManager(paths)
    evidence = {t for m,_ in seed._contracts.values() for t in m["requires_complete"]}
    ids = {}
    for source,binding in paths:
        ids[source.stem], = evaluate(source.read_text(encoding="utf-8"),json.loads(binding.read_text(encoding="utf-8")),baseline).keys()
    all_cases = scenarios(baseline,characterization,evidence)
    # Fixed workload: first duplicate with each dependency size, valid reassignment, coverage fallback.
    cases = [next(c for c in all_cases if c[0].startswith("duplicate:") and c[4]==0),
             next(c for c in all_cases if c[0]=="reassign_valid"),
             next(c for c in all_cases if c[0].startswith("duplicate:") and c[4]==2),
             next(c for c in all_cases if c[0].startswith("duplicate:") and c[4]==30),
             next(c for c in all_cases if c[0]=="fallback:coverage_attested")]
    del all_cases
    files = [p for pair in paths for p in pair]+list((ROOT/"policies").glob("*.safsl"))+list((ROOT/"selira").rglob("*.py"))+list((ROOT/"selira").rglob("*.lark"))+[Path(__file__),ROOT/"evaluation/benchmark_tep.py",ROOT/"evaluation/characterize_tep_nexus.py"]
    config = {"repetitions":args.repetitions,"scenarios":[c[0] for c in cases],
              "inputs":characterization["input_sha256"],
              "code_and_specs":{str(p.resolve().relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "environment":{"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),
                             "dependencies":{p:version(p) for p in ("rdflib","pyshacl","lark")}}}
    if args.resume:
        report = json.loads(args.output.read_text(encoding="utf-8"))
        if report["config"] != config:
            raise ValueError("Checkpoint configuration differs; use original inputs and repetition count")
    else:
        if args.output.exists():
            raise FileExistsError("Output exists; use --resume or a different --output")
        report = {"config":config,"events":[],"initializations":[],"complete":False}
        save(args.output,report)
    done = {(e["repetition"],e["scenario"]) for e in report["events"]}
    options = dict(evidence_complete=evidence,identity_normalized=True,applicability_confirmed=True,
                   coverage_attested=True,policy_unchanged=True,authority_unchanged=True)
    if len(done) < args.repetitions*len(cases):
        init = seed.submit(baseline,expected_version=0,**options)
        assert init["verdict"]=="V" and init["executed_instances"]==182
        report["initializations"].append(init)
        save(args.output,report)
        for rep in range(args.repetitions):
            for j,(name,g,expected,violations,affected,flags) in enumerate(cases):
                if (rep,name) in done:
                    continue
                managers = {s:SelectiveAutomationManager(paths,strategy=s) for s in ("full","selective")}
                for m in managers.values():
                    committed,rev = m.store.compare_and_commit(0,baseline)
                    assert committed and rev==1
                    # Reuse only the verified baseline cache; submit never mutates its dictionaries.
                    m._cache = seed._cache
                order = ("full","selective") if (rep+j)%2==0 else ("selective","full")
                opts = dict(options,expected_version=1)
                opts.update(flags)
                results = {s:managers[s].submit(g,**opts) for s in order}
                verify_pair(results["full"],results["selective"],expected,violations,affected,flags,ids)
                for m in managers.values():
                    after,rev = m.store.snapshot()
                    assert rev==1+int(expected=="V")
                    assert set(after)==set(g if expected=="V" else baseline)
                report["events"].append({"repetition":rep,"scenario":name,"expected":expected,"order":order,**results})
                save(args.output,report)
                print(rep,name,expected,results["selective"]["executed_instances"],"checkpoint saved",flush=True)
    summary = {}
    for name,*_ in cases:
        rows = [e for e in report["events"] if e["scenario"]==name]
        assert len(rows)==args.repetitions
        stats = {}
        for s in ("full","selective"):
            times = [e[s]["elapsed_seconds"] for e in rows]
            stats[s] = {"median_seconds":median(times),"min_seconds":min(times),"max_seconds":max(times),
                        "executed_instances":[e[s]["executed_instances"] for e in rows]}
        stats["speedup"] = stats["full"]["median_seconds"]/stats["selective"]["median_seconds"]
        summary[name] = stats
    report["summary"] = summary
    report["complete"] = True
    save(args.output,report)
    print(json.dumps(summary,indent=2))

if __name__=="__main__":
    main()
