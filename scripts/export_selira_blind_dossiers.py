#!/usr/bin/env python3
"""Export evidence-only review dossiers, with no evaluator predictions."""

# Created: 2026-10-30
# Author: Harish
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
from run_selira_e1_e10_benchmark import synthetic_case

TASKS = ("SOURCE", "CAC-01", "CAC-02")
SC = ("SC-01 identity", "SC-02 quantity", "SC-03 units",
      "SC-04 applicability", "SC-05 binding")


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def generate(report, directory, seed=2027):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cases = ["E" + str(n) for n in range(1, 11)]
    random.Random(seed).shuffle(cases)
    mapping, manifest = {}, []
    for number, case in enumerate(cases, 1):
        alias = "D-" + str(number).zfill(3)
        if case == "E10":
            evidence = {"kind": "focused discovery, not authenticated",
                        "observations": report,
                        "CAC-01 requirements": ["runId", "timeInterval", "units",
                                                "provenance", "measurementCoverage"],
                        "CAC-02 requirements": ["approval", "targetProperty",
                                                "units", "configuration"]}
        else:
            source, consumer = synthetic_case(case)
            evidence = {"kind": "synthetic fixture, not field authentication",
                        "source": [{"contract": name, "input": value}
                                   for name, value in zip(SC, source)],
                        "consumer": consumer}
        dossier = {"dossierId": alias, "tasks": TASKS,
                   "evidence": evidence,
                   "instruction": "Label V/F/U; NA only if CAC is out of scope. "
                                  "Do not infer engineering authorization."}
        data = encode(dossier)
        filename = alias + ".json"
        (directory / filename).write_bytes(data)
        manifest.append({"dossierId": alias, "filename": filename,
                         "sha256": hashlib.sha256(data).hexdigest()})
        mapping[alias] = case
    (directory / "manifest.json").write_bytes(encode(manifest))
    with (directory / "blank-review-form.csv").open(
            "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["dossierId", "task", "reviewerId", "referenceStatus",
                         "evidenceBasis", "reason", "reviewedAt", "adjudicationNotes"])
        for alias in mapping:
            for task in TASKS:
                writer.writerow([alias, task, "", "", "", "", "", ""])
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--reviewer-dir", default="selira-blind-dossiers")
    parser.add_argument("--private-map", default="selira-private-dossier-map.json")
    parser.add_argument("--seed", type=int, default=2027)
    args = parser.parse_args()
    directory = Path(args.reviewer_dir).resolve()
    private = Path(args.private_map).resolve()
    if private == directory or directory in private.parents:
        parser.error("Private mapping must be outside reviewer directory")
    if private.exists():
        parser.error("Private mapping already exists; refusing overwrite")
    with open(args.focused, encoding="utf-8") as stream:
        report = json.load(stream)
    mapping = generate(report, directory, args.seed)
    private.write_bytes(encode(mapping))
    print("Share ONLY reviewer directory:", directory)
    print("Keep private mapping separate:", private)


if __name__ == "__main__":
    main()
