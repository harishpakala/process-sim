"""Validate saved single-domain SPARQL syntax without Ollama or RDF execution.

Execution and semantic correctness are deliberately reported as not_checked.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from process_sim.dtwise.shacl_planner.sparql_validator import validate_syntax


def validate_results(items):
    if not isinstance(items, list):
        raise ValueError("Expected a JSON list of compilation results")
    seen = set()
    results = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Each result needs a string ID")
        if item["id"] in seen:
            raise ValueError("Duplicate result ID: " + item["id"])
        seen.add(item["id"])
        base = {"id": item["id"], "scenario_id": item.get("scenario_id"),
                "domain": item.get("domain"), "compilation_status": item.get("status"),
                "execution_status": "not_checked", "semantic_status": "not_checked"}
        if item.get("status") != "compiled":
            result = {"status": "not_compiled", "error": item.get("error")}
        else:
            result = validate_syntax(item.get("sparql"))
        results.append({**base, **result})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=ROOT /
                    "benchmark_results/single_domain_sparql_results.json")
    ap.add_argument("--output", type=Path, default=ROOT /
                    "benchmark_results/single_domain_sparql_validation.json")
    args = ap.parse_args(argv)
    results = validate_results(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    counts = Counter(r["status"] for r in results)
    print("Summary:", dict(sorted(counts.items())))
    print("Execution: not checked; semantic correctness: not checked")
    print("Output:", args.output)
    return 0 if results and all(r["status"] == "syntax_valid" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
