"""Run paper-relevant checks and compare archived experimental outputs."""
import hashlib
import itertools
import json
import platform
import subprocess
import sys
from pathlib import Path
from importlib.metadata import version

from characterize_dataset import characterize
from selira.runtime.reassessment.snapshot import Snapshot
from selira.runtime.reassessment.selective_sc01 import compare

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/reproduced"
ARCHIVE = ROOT / "evaluation/results/archived"


def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def bounded():
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
                logical_reduction_percent=100*(full-selective)/full)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run("-m", "pytest", "tests", "-q")
    rq3 = bounded()
    characterization = characterize(ROOT / "datasets/tep_nexus")
    assert characterization == read(ARCHIVE / "dataset_characterization.json")
    run("evaluation/multi_contract_baseline.py")
    run("evaluation/multi_contract_lifecycle.py")
    baseline = read(OUT / "multi_contract_baseline.json")
    assert baseline == read(ARCHIVE / "multi_contract_baseline.json"), "Baseline differs"
    current = read(OUT / "multi_contract_lifecycle.json")
    archived = read(ARCHIVE / "multi_contract_lifecycle.json")
    for key in ("scope", "baseline_union_triples", "summary", "events"):
        assert current[key] == archived[key], f"Lifecycle differs: {key}"
    def by_name(hashes):
        return {k.replace(chr(92), "/").split("/")[-1]: v for k, v in hashes.items()}
    assert by_name(current["input_sha256"]) == by_name(archived["input_sha256"])
    paths = sorted(p for folder in ("datasets", "contracts", "bindings", "policies")
                   for p in (ROOT / folder).rglob("*") if p.is_file())
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths}
    report = {
        "regression_suite": "passed",
        "RQ1": {"bounded_configurations": 81, "status": "passed via regression test"},
        "RQ2": {"status": "admission tests passed; original nine-scenario reproduction pending"},
        "RQ3": {"bounded": rq3, "policy_configurations": 80,
                "policy_status": "passed via regression tests"},
        "dataset_characterization": "matches archive",
        "baseline": {"status": "matches archive", "total_focus": baseline["total_focus"]},
        "integrated": current["summary"],
        "integrated_archive_comparison": "passed (excluding environment and path spelling)",
        "input_sha256": hashes,
        "environment": {"python": platform.python_version(),
                        **{p: version(p) for p in ("lark", "rdflib", "pyshacl", "pytest")}},
    }
    (OUT / "verification_report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
