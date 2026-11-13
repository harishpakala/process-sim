"""Paired wording experiment for frozen Experiment 42, unchanged path-only planner.

Run from repository root with local Ollama and GraphDB available:
  $env:PYTHONPATH="$PWD\\src"
  python experiments/vector_graph_rag/42_compare_wording.py --execute

No changes to the API, retrieval, prompt, LLM, or ontology between variants.
Each variant is run using the same in-process planner; no gold accuracy claimed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.api.frozen_benchmark import pilot_questions, run_case

REVISED = {
    "E42-01": "List the equipment records contained in the DEXPI equipment collection, including their identifiers.",
    "E42-02": "Which instrumentation functions are defined in the DEXPI engineering model?",
    "E42-03": "Which equipment records belong to the DEXPI equipment collection, and what collection contains each record?",
    "E42-04": "Which ECAD devices have defined connection points, and what are those connection points?",
    "E42-05": "Which vessels have a documented design-pressure value greater than 10 bar? Return the vessel and pressure value.",
    "E42-06": "Which equipment collections contain individual equipment records in DEXPI?",
    "E42-07": "Which ECAD devices have explicit evidence of physical installation on the reactor? Exclude candidate-only links.",
    "E42-08": "Which engineering equipment records have verified links to both asset inventory and ECAD device records?",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Execute compiled queries against GraphDB")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/vector_graph_rag/data/experiment_42_wording_comparison.json")
    args = parser.parse_args()
    registry = pilot_questions()
    cases = registry["questions"]
    if set(REVISED) != {c["id"] for c in cases}:
        raise RuntimeError("Pilot question set changed; comparison invalid")
    report = {"experiment": 42, "study": "paired_original_vs_clarified_wording",
              "indexSha256": registry["indexSha256"],
              "planner": "unchanged Experiment 36D single-path selector",
              "executionRequested": args.execute,
              "goldAnswersVerified": False, "results": []}
    for case in cases:
        for variant in ("original", "clarified"):
            wording = case["question"] if variant == "original" else REVISED[case["id"]]
            print(f"{case['id']} {variant}: {wording}", flush=True)
            started = time.monotonic()
            try:
                result = run_case(case["id"], registry["indexSha256"],
                                  execute=args.execute, pilot=True,
                                  question_override=wording)
                entry = {"id": case["id"], "variant": variant, "question": wording,
                         "status": "completed", "result": result}
                print(f"  path={result['selectedPathId']} execution={result['execution']} rows={result.get('returnedRows')}", flush=True)
            except Exception as exc:
                entry = {"id": case["id"], "variant": variant, "question": wording,
                         "status": "error", "error": f"{type(exc).__name__}: {exc}"}
                print(f"  ERROR: {entry['error']}", flush=True)
            entry["wallSeconds"] = round(time.monotonic() - started, 2)
            report["results"].append(entry)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pairs = []
    for case in cases:
        original, clarified = [x for x in report["results"] if x["id"] == case["id"]]
        a, b = original.get("result", {}), clarified.get("result", {})
        pairs.append({"id": case["id"],
                      "originalPath": a.get("selectedPathId"),
                      "clarifiedPath": b.get("selectedPathId"),
                      "pathChanged": a.get("selectedPathId") != b.get("selectedPathId"),
                      "bothCompleted": original["status"] == clarified["status"] == "completed",
                      "semanticCorrectness": "NOT_ANNOTATED"})
    report["pairs"] = pairs
    report["summary"] = {"variantsAttempted": len(report["results"]),
                         "completed": sum(x["status"] == "completed" for x in report["results"]),
                         "pairsWithDifferentPath": sum(p["pathChanged"] for p in pairs if p["bothCompleted"]),
                         "verifiedCorrectAnswers": None,
                         "note": "Path changes are not accuracy improvements; manually inspect SPARQL and evidence."}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {args.output}")

if __name__ == "__main__":
    main()
