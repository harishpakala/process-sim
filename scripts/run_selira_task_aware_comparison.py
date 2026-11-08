#!/usr/bin/env python3
"""Run separately scoped SHACL CAC profiles and export blind review templates."""

# Created: 2026-10-30
# Author: Harish
import argparse
import csv
import json
from pathlib import Path
from rdflib import Graph, RDF
from run_selira_semantic_shacl_baseline import (
    ROOT, graph_with_task_scope, validation, SHAPES, SEMANTIC)
from run_selira_shacl_baseline import EX
from run_selira_e1_e10_benchmark import evaluate, synthetic_case

TASK_SHAPES = ROOT / "experiments" / "shacl" / "task-aware-baseline.ttl"
COLUMNS = ("caseId", "task", "reviewerId", "referenceStatus",
           "evidenceBasis", "reason", "reviewedAt", "adjudicationNotes")


def task_validation(case_id, shapes, report=None):
    graph = graph_with_task_scope(case_id, report)
    bundle = EX["bundle-" + case_id]
    results = {}
    for task, task_class in (("CAC-01", EX.CAC01Task), ("CAC-02", EX.CAC02Task)):
        scoped = Graph()
        for triple in graph:
            scoped.add(triple)
        scoped.add((bundle, RDF.type, task_class))
        results[task] = validation(scoped, shapes)
    return results


def build(report):
    shapes = Graph().parse(TASK_SHAPES, format="turtle")
    cases = []
    for index in range(1, 11):
        case_id = "E" + str(index)
        actual = report if index == 10 else None
        outcome = evaluate(case_id, actual)
        cases.append({
            "id": case_id,
            "taskSHACL": task_validation(case_id, shapes, actual),
            "selira": {
                "source": outcome["sourceStatus"],
                "CAC-01": outcome["decision"]["consumers"]["CAC-01"]["decision"],
                "CAC-02": outcome["decision"]["consumers"]["CAC-02"]["decision"],
            },
            "authorization": False,
        })
    return {
        "experiment": "Task-aware SHACL vs SELiRA; reference labels pending",
        "cases": cases,
        "independentReferenceLabelsAvailable": False,
        "limitations": [
            "Task-specific SHACL conformance is not equivalent to three-valued CAC fitness",
            "Review forms are blank: reference labels have not been independently adjudicated",
            "Cases E1-E9 are synthetic and E10 is focused GraphDB discovery",
            "Reviewers should not see SELiRA or SHACL predictions before labeling",
            "Task profiles check presence and explicit violation, not full authority or semantics",
        ],
    }


def export_review_template(path):
    # Only identifiers and tasks; no model-generated labels.
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for index in range(1, 11):
            for task in ("SOURCE", "CAC-01", "CAC-02"):
                writer.writerow({"caseId": "E" + str(index), "task": task})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-task-aware-shacl-results.json")
    parser.add_argument("--review-template", default="selira-blind-review-template.csv")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as stream:
        report = json.load(stream)
    result = build(report)
    with Path(args.output).open("w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    export_review_template(args.review_template)
    for case in result["cases"]:
        print(case["id"], "CAC-01", case["taskSHACL"]["CAC-01"]["conforms"],
              "CAC-02", case["taskSHACL"]["CAC-02"]["conforms"])
    print("Wrote", args.output, "and", args.review_template)


if __name__ == "__main__":
    main()
