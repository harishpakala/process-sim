#!/usr/bin/env python3
"""Run OPC UA ontology-description regression tests against local Ollama and GraphDB.

No instance hints or question-specific translator rules are introduced.
Each translator invocation produces its normal full audit JSON.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATOR = ROOT / "experiments" / "ontology_nl2sparql_generic_v4_1.py"

CASES = [
    ("baseline", "List OPC UA signal names and their node IDs.", "success", 34,
     {"hasSignalName", "hasOPCUANodeId"}),
    ("node_identifier_paraphrase", "List OPC UA signal names and OPC UA node identifiers.", "success", 34,
     {"hasSignalName", "hasOPCUANodeId"}),
    ("endpoint_paraphrase", "Show OPC UA server endpoint URLs and endpoint statuses.", "success", 1,
     {"hasEndpointUrl", "hasEndpointStatus"}),
    ("mapping_status", "List OPC UA signal names and mapping statuses.", "success", 34,
     {"hasSignalName", "hasMappingStatus"}),
    ("reference_distinction", "List OPC UA signal names and engineering function references.", "success", 34,
     {"hasSignalName", "hasEngineeringFunctionReference"}),
    ("removed_function_id", "Within OPC UA Connectivity, list signal names and engineering function IDs.", "reject", None, None),
    ("removed_engineering_domain", "Within OPC UA Connectivity, list signal names and engineering domains.", "reject", None, None),
]


def local(iri):
    return iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def evaluate(case, report):
    name, _, expected, rows, predicates = case
    errors = []
    plan = report.get("plan") or {}
    fields = plan.get("fields") or []
    selected = {local(f.get("predicate", "")) for f in fields if isinstance(f, dict)}
    if report.get("error"):
        errors.append("runtime error: " + str(report["error"]))
    if not report.get("completed"):
        errors.append("Ollama response incomplete")
    if expected == "success":
        if report.get("plan_issues"):
            errors.append("plan rejected: " + str(report["plan_issues"]))
        if not report.get("generated_sparql"):
            errors.append("SPARQL not generated")
        if report.get("binding_count") != rows:
            errors.append("expected %s rows, got %s" % (rows, report.get("binding_count")))
        if selected != predicates:
            errors.append("selected predicates %s; expected %s" % (sorted(selected), sorted(predicates)))
    else:
        if report.get("generated_sparql") is not None:
            errors.append("unsupported request unexpectedly generated SPARQL")
        if not report.get("plan_issues"):
            errors.append("unsupported request not explicitly rejected")
    return {"case": name, "expected": expected, "passed": not errors,
            "selected_predicates": sorted(selected), "rows": report.get("binding_count"),
            "issues": report.get("plan_issues"), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="reports/opcua_description_regression")
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    args = parser.parse_args()
    out = Path(args.output_dir)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for case in CASES:
        name, question, _, _, _ = case
        report_path = out / (name + ".json")
        command = [sys.executable, str(TRANSLATOR), "--question", question,
                   "--model", args.model, "--output", str(report_path)]
        print("\n== %s ==\n%s" % (name, question), flush=True)
        completed = subprocess.run(command, cwd=str(ROOT), check=False)
        if not report_path.exists():
            result = {"case": name, "passed": False, "errors": ["missing report; exit %s" % completed.returncode]}
        else:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            result = evaluate(case, report)
            result["translator_exit_code"] = completed.returncode
            result["report_file"] = str(report_path)
        results.append(result)
        print("PASS" if result["passed"] else "FAIL", result.get("errors", []), flush=True)
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results), "results": results}
    destination = out / "summary.json"
    destination.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\nSummary: %s/%s passed. %s" % (summary["passed"], summary["total"], destination))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
