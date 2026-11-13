"""Smoke-test all eight Experiment 42 questions through the running local API.

Usage:
  python experiments/vector_graph_rag/42_smoke_test_ui.py
  python experiments/vector_graph_rag/42_smoke_test_ui.py --execute

Requires local Python API and Ollama; --execute additionally requires GraphDB.
Reports actual model decisions and errors, not fabricated gold-answer scores.
"""
import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

def request(url, payload=None, timeout=240):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read(3000).decode('utf-8', errors='replace')}") from exc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--execute", action="store_true", help="Run validated SPARQL on GraphDB")
    ap.add_argument("--output", type=Path, default=Path("experiments/vector_graph_rag/data/experiment_42_smoke_results.json"))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    registry = request(base + "/api/ai/benchmarks/42/questions")
    questions = registry["questions"]
    if len(questions) != 8 or len({q["id"] for q in questions}) != 8:
        raise RuntimeError("Expected exactly eight distinct frozen pilot cases")
    if any(q.get("expectedPathId") is not None for q in questions):
        raise RuntimeError("Pilot gold annotations unexpectedly populated")
    report = {"experiment": 42, "indexSha256": registry["indexSha256"],
              "executionRequested": args.execute, "results": []}
    for q in questions:
        started = time.monotonic()
        print(f"{q['id']}: {q['question']}", flush=True)
        try:
            result = request(base + "/api/ai/benchmarks/42/run",
                             {"caseId": q["id"], "indexSha256": registry["indexSha256"],
                              "execute": args.execute})
            if result.get("caseId") != q["id"] or result.get("experiment") != 42:
                raise RuntimeError("Mismatched case or experiment in API response")
            if result.get("correctPathSelection") is not None:
                raise RuntimeError("Pilot incorrectly returned a gold-path score")
            row = {"id": q["id"], "status": "completed", "selectedPathId": result.get("selectedPathId"),
                   "query": result.get("query"), "execution": result.get("execution"),
                   "returnedRows": result.get("returnedRows"), "answer": result.get("answer"),
                   "answerStatus": result.get("answerStatus"), "result": result}
            print(f"  selected={row['selectedPathId']} execution={row['execution']} rows={row['returnedRows']}", flush=True)
        except (RuntimeError, URLError, TimeoutError, ValueError, KeyError) as exc:
            row = {"id": q["id"], "status": "error", "error": str(exc)}
            print(f"  ERROR: {exc}", flush=True)
        row["wallSeconds"] = round(time.monotonic() - started, 2)
        report["results"].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["summary"] = {"completed": sum(r["status"] == "completed" for r in report["results"]),
                         "errors": sum(r["status"] == "error" for r in report["results"]),
                         "verifiedEngineeringAnswers": 0,
                         "note": "Smoke test only; no verified gold answers or pass rate."}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {args.output}")

if __name__ == "__main__":
    main()
