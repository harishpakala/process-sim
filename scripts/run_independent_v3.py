#!/usr/bin/env python3
"""Independent Q1-Q10 runner with ProductCatalog grounding; frozen scripts unchanged."""

# Created: 2026-11-03
# Author: Harish
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.api.catalog_grounding import POLICY, flags

spec = importlib.util.spec_from_file_location("frozen_queries", ROOT / "scripts/tep_nexus_paper_queries.py")
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True)
    p.add_argument("--questions", default="reports/independent_questions_v2.json")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--output", default="reports/independent_v3_results.json")
    args = p.parse_args()
    report = json.loads(Path(args.evidence).read_text(encoding="utf-8-sig"))
    questions = frozen.load_questions(args.questions)
    frozen.ANSWER_SYSTEM_PROMPT += "\n" + POLICY
    frozen.PROMPT_VERSION = "INDEPENDENT_V3_PRODUCTCATALOG_ONLY"
    frozen.ANSWER_PROMPT_SHA256 = hashlib.sha256(
        frozen.ANSWER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    result = frozen.run(report, ollama_url=args.ollama_url, model=args.model,
                        questions=questions)
    counts = {"NO_DETECTED_ISSUES": 0, "REVIEW_REQUIRED": 0}
    for row in result["results"]:
        response = row.get("ollama_answer")
        if response is None:
            issues = ["MODEL_ANSWER_UNAVAILABLE"]
        else:
            issues = flags(response.get("answer"), response.get("limitations"),
                           row.get("evidence") or {}, row["id"])
        row["productcatalog_validation"] = {
            "status": "REVIEW_REQUIRED" if issues else "NO_DETECTED_ISSUES",
            "flags": issues,
            "note": "Conservative heuristic checks; not proof of semantic correctness."
        }
        counts[row["productcatalog_validation"]["status"]] += 1
        if issues:
            # Preserve raw model answer for auditing; never silently mark it correct.
            row["rejected_model_answer"] = response
            row["accepted_answer"] = row["reference_answer"]
            row["accepted_answer_source"] = "DETERMINISTIC_EVIDENCE_FALLBACK"
        else:
            row["accepted_answer"] = response
            row["accepted_answer_source"] = "OLLAMA_HEURISTIC_CHECKS_PASSED"
    result["scope"] = "Independent Q1-Q10 fixed registry; ProductCatalog-only ECLASS policy; correctness not proven"
    result["productcatalog_validation_summary"] = counts
    result["questions_file"] = args.questions
    result["answer_generation_mode"] = "BLIND_EVIDENCE_ONLY_PRODUCTCATALOG_POLICY"
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved", out, counts)
    for row in result["results"]:
        issues = row["productcatalog_validation"]["flags"]
        if issues:
            print(row["id"], ", ".join(issues))


if __name__ == "__main__":
    main()
