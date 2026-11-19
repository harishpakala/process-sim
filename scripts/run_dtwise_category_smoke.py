"""Run one live LLM-driven DTWise benchmark question per manifest category.

Selection is deterministic; query planning is not. Delegates execution to the
existing unified batch runner, preserving its Ollama/SHACL/SPARQL/GraphDB path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend" / "public" / "dtwise-benchmark-manifest.json"
BATCH = ROOT / "scripts" / "run_dtwise_unified_batch.py"
MAPPINGS = ROOT / "semantic" / "ontology2" / "dtwise" / "cross-domain-mappings.json"

# Progression from foundational retrieval to multi-domain reasoning.
CATEGORY_ORDER = (
    "basic", "filters", "multiple_projections", "aggregation",
    "sorting_pagination", "language_variation", "single_domain",
    "string_filtering", "boolean", "cross_domain", "multi_domain_multi_hop",
)


def representatives() -> list[dict]:
    cases = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("Benchmark manifest must be an array")
    by_category: dict[str, dict] = {}
    ids: set[str] = set()
    for case in cases:
        case_id = case["id"]
        if case_id in ids:
            raise ValueError(f"Duplicate benchmark ID: {case_id}")
        ids.add(case_id)
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError(f"Empty question: {case_id}")
        by_category.setdefault(case["category"], case)
    unknown = set(by_category) - set(CATEGORY_ORDER)
    if unknown:
        raise ValueError(f"Unrecognized categories: {sorted(unknown)}")
    missing = set(CATEGORY_ORDER) - set(by_category)
    if missing:
        raise ValueError(f"Missing categories: {sorted(missing)}")
    return [by_category[name] for name in CATEGORY_ORDER]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Show the representative question for each category")
    parser.add_argument("--category", choices=CATEGORY_ORDER, help="Run one category (recommended for step-by-step testing)")
    parser.add_argument("--all-categories", action="store_true", help="Run one representative per category, sequentially")
    parser.add_argument("--endpoint", default=os.environ.get("GRAPHDB_SPARQL_ENDPOINT"))
    parser.add_argument("--mappings", type=Path, default=MAPPINGS,
                        help="Approved ontology2 cross-domain mappings JSON")
    parser.add_argument("--model", default=os.environ.get("DTWISE_UNIFIED_MODEL", "qwen2.5-coder:3b"))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "dtwise_category_smoke")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--llm-timeout", type=int, default=120)
    parser.add_argument("--keep-alive", default="30m")
    parser.add_argument("--no-owner-hints", action="store_true", help="Disable SHACL property-owner hints")
    parser.add_argument("--continue-on-failure", action="store_true", help="Only with --all-categories")
    parser.add_argument("--compact-catalog", action="store_true",
                        help="Experimental lossless SHACL IRI symbol compression")
    parser.add_argument("--prompt-diagnostics", action="store_true",
                        help="Record prompt-size and Ollama request timing diagnostics")
    args = parser.parse_args()

    if args.category and args.all_categories:
        parser.error("Choose either --category or --all-categories")
    if args.continue_on_failure and not args.all_categories:
        parser.error("--continue-on-failure requires --all-categories")
    selected = representatives()
    if args.list:
        for index, case in enumerate(selected, 1):
            print(f"{index:02d}. {case['category']}: {case['id']} — {case['question']}")
        return 0
    if not args.endpoint:
        parser.error("Set GRAPHDB_SPARQL_ENDPOINT or supply --endpoint")
    if not args.category and not args.all_categories:
        parser.error("Specify --category, --all-categories, or --list")
    if args.category:
        selected = [case for case in selected if case["category"] == args.category]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    overview = []
    for index, case in enumerate(selected, 1):
        category, case_id = case["category"], case["id"]
        target = args.output_dir / category
        command = [
            sys.executable, str(BATCH), "--endpoint", args.endpoint,
            "--model", args.model, "--ollama-host", args.ollama_host,
            "--start", str(int(case_id[1:])), "--end", str(int(case_id[1:])),
            "--timeout", str(args.timeout), "--llm-timeout", str(args.llm_timeout),
            "--output-dir", str(target), "--mappings", str(args.mappings),
        ]
        if args.compact_catalog:
            command.append("--compact-catalog")
        if args.prompt_diagnostics:
            command.append("--prompt-diagnostics")
        if not args.no_owner_hints:
            command.append("--owner-hints")
        if args.keep_alive:
            command.extend(["--keep-alive", args.keep_alive])
        print(f"\n[{index}/{len(selected)}] {category} — {case_id}: {case['question']}", flush=True)
        process = subprocess.run(command, cwd=ROOT)
        summary_path = target / "summary.json"
        result = None
        if summary_path.exists():
            try:
                rows = json.loads(summary_path.read_text(encoding="utf-8"))
                if rows and rows[0].get("id") == case_id:
                    result = rows[0]
            except (ValueError, OSError):
                pass
        status = result.get("status", "ERROR") if result else "ERROR"
        overview.append({
            "category": category, "id": case_id, "question": case["question"],
            "status": status, "seconds": result.get("seconds") if result else None,
            "rows": result.get("result_rows") if result else None,
            "error": result.get("error", "") if result else f"Batch runner exited {process.returncode}; inspect logs",
            "summary_file": str(summary_path),
            "semantic_verification": "PENDING_REVIEW",
        })
        (args.output_dir / "category_summary.json").write_text(
            json.dumps(overview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Category result: {category} — {status}", flush=True)
        if status != "EXECUTED_REVIEW_PENDING" and not args.continue_on_failure:
            print("Stopped at first failure. Inspect category report before proceeding.")
            return 1
    print(f"\nCategory summary: {args.output_dir / 'category_summary.json'}")
    print("Execution is not proof of semantic correctness.")
    return 0 if all(row["status"] == "EXECUTED_REVIEW_PENDING" for row in overview) else 1


if __name__ == "__main__":
    raise SystemExit(main())
