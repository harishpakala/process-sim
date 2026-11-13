#!/usr/bin/env python3
"""ECAD description-grounding regression against local Ollama and GraphDB.

Measures predicate selection, validation, SPARQL compilation, and execution
separately. Expected predicates are evaluation-only, not translator hints.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATOR = ROOT / "experiments" / "ontology_nl2sparql_generic_v4_1.py"

# All questions target one ECAD element type or one unambiguous property pair.
# Counts are measured, not asserted, because they depend on instance RDF.
CASES = [
    ("device_local_ids", "List local IDs of ECAD devices.",
     {"hasLocalId"}),
    ("device_asset_identifiers", "List asset identifiers of ECAD devices.",
     {"hasAssetIdentifier"}),
    ("device_engineering_verification", "List engineering verification statuses and engineering verification evidence of ECAD devices.",
     {"hasEngineeringVerificationStatus", "hasEngineeringVerificationEvidence"}),
    ("device_product_verification", "List product verification statuses and product verification evidence of ECAD devices.",
     {"hasProductVerificationStatus", "hasProductVerificationEvidence"}),
    ("device_association", "List related asset identifiers and cross-domain association evidence of ECAD devices.",
     {"hasRelatedAssetIdentifier", "hasCrossDomainAssociationEvidence"}),
]


def local(iri):
    return str(iri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def evaluate(name, expected, report):
    plan = report.get("plan") or {}
    fields = plan.get("fields") or []
    selected = {local(f.get("predicate", "")) for f in fields if isinstance(f, dict)}
    issues = report.get("plan_issues") or []
    sparql = report.get("generated_sparql")
    rows = report.get("binding_count")
    result = {
        "case": name,
        "completed": bool(report.get("completed")),
        "expected_predicates": sorted(expected),
        "selected_predicates": sorted(selected),
        "predicate_selection_correct": selected == expected,
        "validator_accepted": not issues,
        "sparql_generated": bool(sparql),
        "execution_succeeded": isinstance(rows, int) and report.get("error") is None,
        "nonempty_results": isinstance(rows, int) and rows > 0,
        "binding_count": rows,
        "plan_issues": issues,
        "error": report.get("error"),
    }
    result["passed"] = all((
        result["completed"], result["predicate_selection_correct"],
        result["validator_accepted"], result["sparql_generated"],
        result["execution_succeeded"],
    ))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="reports/ecad_description_regression")
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    parser.add_argument("--max-shapes", type=int, default=10)
    args = parser.parse_args()
    out = Path(args.output_dir)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name, question, expected in CASES:
        report_path = out / (name + ".json")
        if report_path.exists():
            report_path.unlink()
        command = [
            sys.executable, str(TRANSLATOR), "--question", question,
            "--model", args.model, "--max-shapes", str(args.max_shapes),
            "--output", str(report_path),
        ]
        print("\n== %s ==\n%s" % (name, question), flush=True)
        process = subprocess.run(command, cwd=str(ROOT), check=False)
        if not report_path.exists():
            result = {"case": name, "passed": False, "error": "No audit report generated"}
        else:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            result = evaluate(name, expected, report)
        result["translator_exit_code"] = process.returncode
        result["report_file"] = str(report_path)
        results.append(result)
        print("PASS" if result["passed"] else "FAIL", flush=True)
    summary = {
        "domain": "ECAD",
        "model": args.model,
        "total": len(results),
        "passed": sum(bool(r["passed"]) for r in results),
        "predicate_selection_correct": sum(bool(r.get("predicate_selection_correct")) for r in results),
        "validator_accepted": sum(bool(r.get("validator_accepted")) for r in results),
        "sparql_generated": sum(bool(r.get("sparql_generated")) for r in results),
        "execution_succeeded": sum(bool(r.get("execution_succeeded")) for r in results),
        "nonempty_results": sum(bool(r.get("nonempty_results")) for r in results),
        "results": results,
    }
    destination = out / "summary.json"
    destination.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\nSummary: %d/%d passed. %s" % (summary["passed"], summary["total"], destination))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
