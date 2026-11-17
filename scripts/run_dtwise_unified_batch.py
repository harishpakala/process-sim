"""Run existing DTWise benchmark questions through the live Unified IR CLI.

No query generation, semantic rewriting, SELiRA access, or fixture modification.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend" / "public" / "dtwise-benchmark-manifest.json"
SCHEMA = ROOT / "semantic" / "ontology2" / "dtwise" / "dtwise-schema-index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("GRAPHDB_SPARQL_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("DTWISE_UNIFIED_MODEL", "qwen2.5-coder:3b"))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "dtwise_unified_batch")
    parser.add_argument("--all", action="store_true", help="Run all existing manifest questions, not just B01-B10")
    parser.add_argument("--start", type=int, help="First benchmark number to include (inclusive)")
    parser.add_argument("--end", type=int, help="Last benchmark number to include (inclusive)")
    parser.add_argument("--timeout", type=int, default=240, help="Maximum wall time per question (seconds)")
    parser.add_argument("--llm-timeout", type=int, default=120,
                        help="Ollama HTTP timeout per planning attempt (seconds; default: 120)")
    parser.add_argument("--llm-timeout", type=int, default=120,
                        help="Ollama HTTP timeout per planning attempt (seconds; default: 120)")
    args = parser.parse_args()

    if not args.endpoint:
        parser.error("Set GRAPHDB_SPARQL_ENDPOINT or supply --endpoint")
    if not SCHEMA.is_file():
        parser.error(f"Missing schema index: {SCHEMA}")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    if args.llm_timeout < 1:
        parser.error("--llm-timeout must be positive")
    if args.llm_timeout < 1:
        parser.error("--llm-timeout must be positive")

    if (args.start is None) != (args.end is None):
        parser.error("--start and --end must be supplied together")
    if args.start is not None and (args.start < 1 or args.end < args.start):
        parser.error("Require 1 <= --start <= --end")
    if args.all and args.start is not None:
        parser.error("--all cannot be combined with --start/--end")

    questions = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lower, upper = ((args.start, args.end) if args.start is not None
                    else (None, None) if args.all else (1, 10))
    cases = [q for q in questions if q["id"].startswith("B") and q["id"][1:].isdigit()
             and (lower is None or lower <= int(q["id"][1:]) <= upper)]
    cases.sort(key=lambda q: int(q["id"][1:]))
    if not cases:
        parser.error("No benchmark questions selected")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for index, case in enumerate(cases, 1):
        case_id = case["id"]
        report_path = args.output_dir / f"{case_id}.json"
        log_path = args.output_dir / f"{case_id}.log"
        report_path.unlink(missing_ok=True)
        print(f"[{index}/{len(cases)}] {case_id}: {case['question']}", flush=True)
        command = [
            sys.executable, "-m", "process_sim.dtwise.unified_answer", "answer",
            "--schema", str(SCHEMA), "--question", case["question"],
            "--model", args.model, "--ollama-host", args.ollama_host,
            "--llm-timeout", str(args.llm_timeout),
            "--llm-timeout", str(args.llm_timeout),
            "--endpoint", args.endpoint, "--output", str(report_path),
        ]
        start = time.perf_counter()
        status, error, result_count, exit_code = "ERROR", "", None, None
        try:
            proc = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=args.timeout,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")},
            )
            exit_code = proc.returncode
            log_path.write_text(proc.stdout + "\n--- STDERR ---\n" + proc.stderr, encoding="utf-8")
            if report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if proc.returncode == 0 and report.get("status") == "executed":
                    status = "EXECUTED_REVIEW_PENDING"
                    bindings = report.get("results", {}).get("results", {}).get("bindings", [])
                    result_count = len(bindings)
                else:
                    error = str(report.get("error", "CLI did not confirm execution"))
                    lower = error.lower()
                    status = ("REJECTED" if any(term in lower for term in (
                        "shacl", "validation", "planner rejected", "semantic coverage",
                        "invalid ir", "unsupported", "failed to generate valid unified ir",
                        "unknown", "ambiguous")) else "ERROR")
            else:
                error = "CLI did not write a JSON report; inspect log"
        except subprocess.TimeoutExpired as exc:
            status = "TIMEOUT"
            error = f"Exceeded {args.timeout} seconds"
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            log_path.write_text(stdout + "\n--- STDERR ---\n" + stderr, encoding="utf-8")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error = str(exc)
            log_path.write_text(error, encoding="utf-8")
        elapsed = round(time.perf_counter() - start, 2)
        summary.append({
            "id": case_id, "category": case["category"], "question": case["question"],
            "model": args.model, "llm_timeout_seconds": args.llm_timeout,
            "status": status, "seconds": elapsed, "result_rows": result_count,
            "exit_code": exit_code, "error": error,
            "report_file": str(report_path), "log_file": str(log_path),
            "semantic_verification": "PENDING_REVIEW",
        })
        print(f"  {status} | {elapsed:.2f}s | rows={result_count} | {error[:160]}", flush=True)
        write_reports(args.output_dir, summary)

    print(f"\nFinished {len(summary)} cases. Summary: {args.output_dir / 'summary.csv'}")
    print("EXECUTED_REVIEW_PENDING does not imply semantic correctness.")
    return 0


def write_reports(output_dir: Path, rows: list[dict]) -> None:
    (output_dir / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
