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
MAPPINGS = ROOT / "semantic" / "ontology2" / "dtwise" / "cross-domain-mappings.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("GRAPHDB_SPARQL_ENDPOINT"))
    parser.add_argument("--mappings", type=Path, default=MAPPINGS,
                        help="Approved ontology2 mapping registry JSON")
    parser.add_argument("--model", default=os.environ.get("DTWISE_UNIFIED_MODEL", "qwen2.5-coder:3b"))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "dtwise_unified_batch")
    parser.add_argument("--all", action="store_true", help="Run all existing manifest questions, not just B01-B10")
    parser.add_argument("--start", type=int, help="First benchmark number to include (inclusive)")
    parser.add_argument("--end", type=int, help="Last benchmark number to include (inclusive)")
    parser.add_argument("--timeout", type=int, default=240, help="Maximum wall time per question (seconds)")
    parser.add_argument("--owner-hints", action="store_true",
                        help="Opt-in SHACL property-owner hints for planner")
    parser.add_argument("--compact-catalog", action="store_true",
                        help="Use experimental lossless SHACL IRI symbols")
    parser.add_argument("--compact-prompt", action="store_true",
                        help="Opt-in shorter planner prompt for A/B latency tests")
    parser.add_argument("--keep-alive", default=None,
                        help="Ollama model residency, e.g. 30m")
    parser.add_argument("--llm-timeout", type=int, default=120,
                        help="Ollama HTTP timeout per planning attempt (seconds; default: 120)")
    parser.add_argument("--prompt-diagnostics", action="store_true",
                        help="Write prompt-size and Ollama request timing diagnostics per question")
    args = parser.parse_args()

    if not args.endpoint:
        parser.error("Set GRAPHDB_SPARQL_ENDPOINT or supply --endpoint")
    if not args.mappings.is_file():
        parser.error(f"Missing mapping registry: {args.mappings}")
    if not SCHEMA.is_file():
        parser.error(f"Missing schema index: {SCHEMA}")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
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
            "--endpoint", args.endpoint, "--output", str(report_path),
            "--mappings", str(args.mappings),
        ]
        if args.prompt_diagnostics:
            command.extend(["--prompt-diagnostics", str(args.output_dir / f"{case_id}.prompt-diagnostics.json")])
        if args.owner_hints:
            command.append("--owner-hints")
        if args.compact_catalog:
            command.append("--compact-catalog")
        if args.compact_prompt:
            command.append("--compact-prompt")
        if args.keep_alive is not None:
            command.extend(["--keep-alive", args.keep_alive])
        start = time.perf_counter()
        status, error, result_count, exit_code = "ERROR", "", None, None
        planning_seconds = compilation_seconds = graphdb_seconds = None
        llm_attempts = llm_seconds = prompt_tokens = generated_tokens = None
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
                timings = report.get("timings", {})
                planning_seconds = timings.get("planning_seconds")
                compilation_seconds = timings.get("compilation_seconds")
                graphdb_seconds = timings.get("graphdb_seconds")
                attempts = report.get("planning_attempts", [])
                llm_attempts = len(attempts)
                llm_seconds = round(sum(a.get("wall_seconds", 0) for a in attempts), 3)
                prompt_tokens = sum(a.get("prompt_tokens") or 0 for a in attempts)
                generated_tokens = sum(a.get("generated_tokens") or 0 for a in attempts)
                if proc.returncode == 0 and report.get("status") == "executed":
                    status = "EXECUTED_REVIEW_PENDING"
                    bindings = report.get("results", {}).get("results", {}).get("bindings", [])
                    result_count = len(bindings)
                else:
                    error = str(report.get("error", "CLI did not confirm execution"))
                    error_lower = error.lower()
                    status = ("REJECTED" if any(term in error_lower for term in (
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
            "compact_prompt": args.compact_prompt, "compact_catalog": args.compact_catalog, "keep_alive": args.keep_alive,
            "owner_hints": args.owner_hints,
            "status": status, "seconds": elapsed, "result_rows": result_count,
            "planning_seconds": planning_seconds, "compilation_seconds": compilation_seconds,
            "graphdb_seconds": graphdb_seconds, "llm_attempts": llm_attempts,
            "llm_seconds": llm_seconds, "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "exit_code": exit_code, "error": error,
            "report_file": str(report_path), "log_file": str(log_path),
            "semantic_verification": "PENDING_REVIEW",
        })
        print(f"  {status} | {elapsed:.2f}s total | planning={planning_seconds}s "
              f"| GraphDB={graphdb_seconds}s | LLM attempts={llm_attempts} "
              f"| rows={result_count} | {error[:160]}", flush=True)
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
