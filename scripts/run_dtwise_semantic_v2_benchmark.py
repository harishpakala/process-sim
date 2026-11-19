"""Run the canonical DTWise manifest through the opt-in Semantic v2 CLI.

No synthetic expected answers: answer correctness is unverified without an oracle.
Run from the repository root with python scripts/run_dtwise_semantic_v2_benchmark.py.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_MANIFEST = Path("frontend/public/dtwise-benchmark-manifest.json")


def load_cases(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(cases, list) or len(cases) != 53
            or any(not isinstance(case, dict)
                   or not isinstance(case.get("id"), str)
                   or not isinstance(case.get("question"), str)
                   or not case["question"].strip() for case in cases)
            or len({case["id"] for case in cases}) != len(cases)):
        raise ValueError("Expected 53 uniquely identified benchmark questions")
    return cases


def evaluate_case(case, args, runner=subprocess.run):
    command = [
        sys.executable, "-m", "process_sim.dtwise.unified_answer",
        "answer" if args.endpoint else "compile",
        "--schema", args.schema,
        "--question", case["question"],
        "--experimental-multihop", "--planning-mode", "semantic_v2",
        "--model", args.model, "--ollama-host", args.ollama_host,
        "--llm-timeout", str(args.llm_timeout),
        "--graph-mode", args.graph_mode,
    ]
    if args.mappings:
        command.extend(["--mappings", args.mappings])
    if args.endpoint:
        command.extend(["--endpoint", args.endpoint])
    if args.keep_alive:
        command.extend(["--keep-alive", args.keep_alive])
    try:
        proc = runner(command, capture_output=True, text=True,
                      encoding="utf-8", errors="replace",
                      timeout=args.case_timeout)
    except subprocess.TimeoutExpired:
        return {"id": case["id"], "category": case.get("category"),
                "question": case["question"], "status": "timeout",
                "planning": "unknown", "compilation": "unknown",
                "execution": "unknown", "answer_correctness": "unverified"}
    try:
        report = json.loads(proc.stdout)
    except (ValueError, TypeError):
        report = {"status": "invalid_cli_output",
                  "error": (proc.stderr or proc.stdout)[-2000:]}
    status = report.get("status")
    timings = report.get("timings", {})
    planned = "passed" if "planning_seconds" in timings else "failed_or_unknown"
    compiled = "passed" if status in ("compiled", "executed") else "failed_or_unknown"
    executed = ("passed" if status == "executed" else
                "not_run" if not args.endpoint else "failed_or_unknown")
    return {
        "id": case["id"], "category": case.get("category"),
        "question": case["question"], "status": status,
        "planning": planned, "compilation": compiled,
        "execution": executed, "answer_correctness": "unverified",
        "returncode": proc.returncode,
        "error": report.get("error"),
        "timings": timings,
        "ir": report.get("ir"),
        "sparql": report.get("sparql"),
        "results": report.get("results"),
        "planning_attempts": report.get("planning_attempts"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--schema", required=True)
    parser.add_argument("--mappings")
    parser.add_argument("--endpoint")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--llm-timeout", type=int, default=120)
    parser.add_argument("--case-timeout", type=int, default=300)
    parser.add_argument("--keep-alive")
    parser.add_argument("--graph-mode", choices=["default", "all_named", "selected"],
                        default="all_named")
    parser.add_argument("--output", default="dtwise-semantic-v2-benchmark.json")
    parser.add_argument("--ids", nargs="*", help="Optional benchmark IDs, e.g. B01 B32")
    args = parser.parse_args(argv)
    if args.llm_timeout < 1 or args.case_timeout < 1:
        parser.error("Timeouts must be positive")
    if not Path(args.schema).is_file():
        parser.error("Schema file does not exist: " + args.schema)
    if args.mappings and not Path(args.mappings).is_file():
        parser.error("Mapping registry file does not exist: " + args.mappings)
    cases = load_cases(args.manifest)
    if args.ids:
        unknown = set(args.ids) - {case["id"] for case in cases}
        if unknown:
            parser.error("Unknown benchmark IDs: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in args.ids]
    rows = []
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        row = evaluate_case(case, args)
        rows.append(row)
        output_path.write_text(json.dumps({
            "mode": "semantic_v2", "requested": len(cases),
            "completed": len(rows),
            "planning_passed": sum(x["planning"] == "passed" for x in rows),
            "compiled": sum(x["compilation"] == "passed" for x in rows),
            "executed": sum(x["execution"] == "passed" for x in rows),
            "answer_correctness": "unverified_no_oracle",
            "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f'{case["id"]}: {row["status"]}', flush=True)
        if row["status"] == "invalid_cli_output" and row.get("error"):
            print("  CLI error: " + row["error"][-1000:], flush=True)
    return 0 if all(x["compilation"] == "passed"
                    and (not args.endpoint or x["execution"] == "passed")
                    for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
