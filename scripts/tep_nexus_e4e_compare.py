#!/usr/bin/env python3
"""Read-only E4-E evidence collection for original and revised question sets.

Does not invoke an LLM or automatically assign PASS/PARTIAL/FAIL.
"""
import argparse
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", default="53b37c4d-b8ba-4e37-8f49-6765a156dc17")
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--asset-inventory", default="examples/aas/asset_inventory_instance.json")
    p.add_argument("--product-catalog", default="examples/aas/product_catalog_instance.json")
    p.add_argument("--output-root", default="reports/e4e_comparison")
    args = p.parse_args()

    spec = importlib.util.spec_from_file_location(
        "tep_nexus_paper_evaluation", ROOT / "scripts/tep_nexus_paper_evaluation.py")
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    engineering = evaluator.engineering_evidence(args.asset_inventory, args.product_catalog)
    temporal = None
    if args.run_id:
        dsn = os.getenv("TEP_TIMESCALE_DSN")
        if not dsn:
            p.error("TEP_TIMESCALE_DSN must be set")
        temporal = evaluator.temporal_evidence(
            dsn, args.run_id, [item[2] for item in evaluator.ASSETS.values()])
    graph = (evaluator.verified_graphdb_mappings(args.graphdb_url)
             if args.graphdb_url else None)
    evidence = evaluator.evaluate(engineering, temporal, graph)

    for version in ("original", "revised"):
        source = ROOT / "docs" / "e4e_tests" / (version + "_questions.json")
        questions = json.loads(source.read_text(encoding="utf-8"))["questions"]
        if len(questions) != 10 or [q["id"] for q in questions] != [
                f"Q{i}" for i in range(1, 11)]:
            raise ValueError("Expected ten ordered Q1-Q10 questions")
        rows = []
        for question, record in zip(questions, evidence):
            rows.append({
                **question,
                "required_sources": record["required_sources"],
                "evidence_status": record["status"],
                "evidence": record.get("evidence"),
                "evidence_reason": record.get("reason"),
                "answer_text": None,
                "manual_assessment": None,
                "assessment_justification": None,
            })
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "version": version, "run_id": args.run_id,
            "scope": "read_only_evidence_not_question_execution_or_automated_scoring",
            "assessment_status": "NOT_ASSESSED",
            "results": rows,
            "limitations": [
                "The questions are not submitted to an LLM by this script.",
                "Evidence availability is not natural-language answer correctness.",
                "Revised Q5 and Q8 are not predetermined PARTIAL.",
                "A recorded fault-injection command does not prove fault activation.",
                "Product associations are not verified physical installations.",
            ],
        }
        target = Path(args.output_root) / version / "evidence_and_assessment_template.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{version}: {sum(r['evidence_status'] == 'EVIDENCE_AVAILABLE' for r in rows)}/10 evidence available; {target}")

if __name__ == "__main__":
    main()
