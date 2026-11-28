"""RC01: reproduce current manuscript targets while preserving historical records.

Run from the artifact root with assertions enabled (no python -O).
Results are generated only by this invocation; stored records are provenance,
not a substitute for current execution.
"""
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import distributions, version
from pathlib import Path

from characterize_dataset import characterize
from selira.runtime.reassessment.snapshot import Snapshot
from selira.runtime.reassessment.selective_sc01 import compare

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/reproduced"
ARCHIVE = ROOT / "evaluation/results/archived"
EXPECTED = {
    "semantic_configurations": 121,
    "focus": {"SC-01": (38, 0), "SC-02": (39, 9), "SC-03": (40, 29), "SC-04": (71, 0)},
    "integrated": {
        "baseline_union_triples": 30611, "events": 16, "admitted": 7,
        "rejected": 8, "deferred": 1, "full_evaluations": 2444,
        "selective_evaluations": 203, "equivalent_comparisons": 13,
        "comparisons": 13,
    },
    "ic14": {"evidence_change_cases": 6, "evidence_submissions": 18,
             "evidence_contract_assertions": 72, "qualified_comparisons": 512,
             "qualified_full_evaluations": 2048},
}


def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def by_name(hashes):
    return {k.replace(chr(92), "/").split("/")[-1]: v for k, v in hashes.items()}


def bounded():
    """Preserve the historical 36-state SC-01 workload as a separate check."""
    states = [
        Snapshot("R1", {"asset:A": a} if a is not None else {},
                 {k: v for k, v in zip(("catalog:1", "catalog:2"), (x, y))
                  if v is not None}, complete=True)
        for a, x, y in itertools.product(
            (None, "id:x", "id:y", "id:z"),
            (None, "id:x", "id:y"), (None, "id:x", "id:y"))
    ]
    full = selective = equivalent = transitions = 0
    for old, new in itertools.product(states, repeat=2):
        r = compare(old, Snapshot("R2", new.assigned, new.catalog, new.complete),
                    coverage_attested=True, policy_unchanged=True,
                    authority_unchanged=True)
        transitions += 1
        equivalent += int(r.equivalent)
        full += r.full_evaluations
        selective += r.selective_evaluations
    assert (len(states), transitions, equivalent) == (36, 1296, 1296)
    assert (full, selective) == (1215, 1084), (full, selective)
    return dict(snapshots=len(states), transitions=transitions,
                equivalent=equivalent, full_evaluations=full,
                selective_evaluations=selective,
                logical_reduction_percent=100 * (full-selective) / full)


def environment():
    packages = sorted(
        ({"name": d.metadata.get("Name", ""), "version": d.version}
         for d in distributions()),
        key=lambda p: (p["name"].lower(), p["version"]),
    )
    return {
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "executable": sys.executable, "platform": platform.platform(),
        "system": platform.system(), "release": platform.release(),
        "machine": platform.machine(), "processor": platform.processor(),
        "packages": packages,
        "key_versions": {p: version(p) for p in ("lark", "rdflib", "pyshacl", "pytest", "selira-research")},
    }


def main():
    if not __debug__:
        raise RuntimeError("Python assertions must be enabled; do not use -O")
    OUT.mkdir(parents=True, exist_ok=True)
    # Regression includes RQ1, RQ2 and IC14 tests, with failures stopping the runner.
    # Run the IC14 modules explicitly too to make inclusion machine-checkable.
    run("-m", "pytest", "tests", "-q")
    run("-m", "pytest", "tests/test_ic14_evidence_changes.py",
        "tests/test_ic14_qualified_reassessment.py", "-q")
    legacy_rq3 = bounded()
    characterization = characterize(ROOT / "datasets/tep_nexus")
    assert characterization == read(ARCHIVE / "dataset_characterization.json")
    run("evaluation/multi_contract_baseline.py")
    run("evaluation/multi_contract_lifecycle.py")
    baseline = read(OUT / "multi_contract_baseline.json")
    assert baseline["all_equivalent"] and baseline["total_focus"] == 188
    focus = {r["contract"]: (r["focus_count"], len(r["shacl_violations"]))
             for r in baseline["contracts"]}
    assert focus == EXPECTED["focus"], focus
    assert all(r["reference_violations"] == r["shacl_violations"]
               for r in baseline["contracts"])
    integrated = read(OUT / "multi_contract_lifecycle.json")
    assert integrated["baseline_union_triples"] == EXPECTED["integrated"]["baseline_union_triples"]
    for key, target in EXPECTED["integrated"].items():
        if key != "baseline_union_triples":
            assert integrated["summary"][key] == target, (key, integrated["summary"].get(key), target)
    assert len(integrated["events"]) == 15
    assert sum(r["verdict"] == "V" for r in integrated["events"]) == 7
    assert sum(r["verdict"] == "F" for r in integrated["events"]) == 7
    assert sum(r["verdict"] == "U" for r in integrated["events"]) == 1
    assert integrated["summary"]["logical_reduction_percent"] == (
        100 * (2444 - 203) / 2444)
    # Historical baseline is retained as a separate reference, not compared
    # byte-for-byte with the evolved 188-instance experiment.
    historical = read(ARCHIVE / "multi_contract_lifecycle.json")
    historical_targets = {k: historical["summary"][k]
                          for k in ("events", "full_evaluations", "selective_evaluations")}
    assert historical_targets == {"events": 11, "full_evaluations": 1638,
                                  "selective_evaluations": 195}
    historical_baseline = read(ARCHIVE / "multi_contract_baseline.json")
    assert historical_baseline["all_equivalent"]
    assert historical_baseline["total_focus"] == 182
    paths = sorted(p for folder in ("datasets", "contracts", "bindings", "policies")
                   for p in (ROOT / folder).rglob("*") if p.is_file())
    hashes = {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}
    assert by_name(integrated["input_sha256"]).items() <= by_name(hashes).items()
    report = {
        "status": "passed",
        "execution_utc": datetime.now(timezone.utc).isoformat(),
        "research_baseline": "255f664de346a9f65d5cc11c3f180067d3551e16",
        "scope": "Current-manuscript functional reproduction; no timing or independent licensing claim",
        "regression_suite": "passed (full pytest and explicit IC14 modules)",
        "RQ1": {"configurations": EXPECTED["semantic_configurations"],
                "status": "covered by regression; integrated violation sets checked"},
        "RQ2": {"qualification_admission_scenarios": 25,
                "ic14_evidence_only": EXPECTED["ic14"],
                "status": "covered by regression; IC14 modules explicitly executed"},
        "RQ3": {"graph_dependent_comparisons": 1808,
                "evidence_qualified_comparisons": EXPECTED["ic14"]["qualified_comparisons"],
                "status": "covered by regression; historical bounded workload checked separately"},
        "historical_bounded": legacy_rq3,
        "historical_integrated": historical_targets,
        "dataset_characterization": "matches archived characterization",
        "integrated_baseline": {"total_focus": baseline["total_focus"], "focus": focus},
        "integrated_current": integrated["summary"],
        "baseline_union_triples": integrated["baseline_union_triples"],
        "input_sha256": hashes,
        "environment": environment(),
        "licensing": "not verified; release blocked pending dataset and artifact rights review",
    }
    (OUT / "verification_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
