"""Run six user-authored Experiment 42 Revision B questions with the UNCHANGED path planner.

From repository root:
    $env:PYTHONPATH="$PWD\\src"
    python experiments/vector_graph_rag/42_revision_b_test.py --execute

Requires Ollama; --execute also requires GraphDB. Original E42 questions remain
unchanged. This is a diagnostic, NOT a gold-answer benchmark.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.api.frozen_benchmark import pilot_questions, run_case

QUESTIONS = [
    ("E42-01", "List all the equipment contained in the DEXPI representation, including their identifiers."),
    ("E42-02", "Which instrumentation functions are defined in the DEXPI representation ?"),
    ("E42-03", "List all the ECAD Devices."),
    ("E42-04", "What are the corresponding ECAD device identifiers for the reactor pressure, feed-flow, temperature, and level instruments?"),
    ("E42-05", "What are the canonical AAS AssetIdentifiers and operational TEP signal references for the reactor pressure, feed-flow, temperature, and level instruments?"),
    ("E42-06", "What DEXPI, ECAD, AssetInventory, ProductCatalog, and operational signal information is available for reactor pressure instrument PI-1101?"),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Execute generated SPARQL against GraphDB")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/vector_graph_rag/data/experiment_42_revision_b_results.json")
    args = parser.parse_args()
    registry = pilot_questions()
    report = {"experiment": 42, "revision": "B", "dataset": "six_user_authored_questions",
              "indexSha256": registry["indexSha256"],
              "planner": "unchanged 36D single-path selector",
              "executionRequested": args.execute,
              "goldAnswersVerified": False, "results": []}
    for case_id, question in QUESTIONS:
        print(f"{case_id}: {question}", flush=True)
        started = time.monotonic()
        try:
            result = run_case(case_id, registry["indexSha256"], execute=args.execute,
                              pilot=True, question_override=question)
            row = {"id": case_id, "question": question, "status": "completed",
                   "selectedPathId": result.get("selectedPathId"),
                   "execution": result.get("execution"), "returnedRows": result.get("returnedRows"),
                   "answerStatus": result.get("answerStatus"), "result": result}
            print(f"  path={row['selectedPathId']} execution={row['execution']} rows={row['returnedRows']}", flush=True)
        except Exception as exc:
            row = {"id": case_id, "question": question, "status": "error",
                   "error": f"{type(exc).__name__}: {exc}"}
            print(f"  ERROR: {row['error']}", flush=True)
        row["wallSeconds"] = round(time.monotonic() - started, 2)
        report["results"].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["summary"] = {
        "attempted": len(report["results"]),
        "completed": sum(r["status"] == "completed" for r in report["results"]),
        "errors": sum(r["status"] == "error" for r in report["results"]),
        "verifiedCorrectAnswers": None,
        "note": "Execution success does not establish answer correctness; inspect predicates, joins, identifiers and bindings."
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {args.output}")

if __name__ == "__main__":
    main()
