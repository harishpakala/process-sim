#!/usr/bin/env python3
"""Run the eight-question V4.1 pilot locally against Ollama and GraphDB.

No expected answer is assumed. The report separates grounding, execution,
and independent answer review (which remains NOT_EVALUATED).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from q13_extract_focused_schema import ROOT, extract


def preflight(case, schema):
    domains = {d["domain"]: d for d in schema["domains"]}
    domain = domains.get(case["domain"])
    if domain is None:
        return "Unknown domain: " + case["domain"]
    owners = [
        shape for shape in domain["node_shapes"]
        if any(p["predicate"].rsplit("#", 1)[-1].rsplit("/", 1)[-1]
               == case["expected_predicate_local"] for p in shape["properties"])
    ]
    return None if owners else "Expected predicate missing from domain SHACL shapes"


def evaluate(case, report):
    """Assess grounding separately from answer correctness."""
    plan = report.get("plan") or {}
    cat = report.get("candidate_shapes") or {}
    fields = plan.get("fields") or []
    matches = [
        f for f in fields
        if isinstance(f, dict)
        and f.get("shape") in cat
        and cat[f["shape"]]["domain"] == case["domain"]
        and f.get("predicate", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        == case["expected_predicate_local"]
    ]
    issues = report.get("plan_issues") or []
    generated = bool(report.get("generated_sparql"))
    no_joins = not report.get("selected_joins")
    grounded = bool(matches and len(fields) == 1 and not issues and generated and no_joins)
    executed = report.get("binding_count") is not None and not report.get("error")
    return {
        "schema_grounding_pass": grounded,
        "execution_success": executed,
        "binding_count": report.get("binding_count"),
        "answer_correctness": "NOT_EVALUATED",
        "error": report.get("error"),
        "plan_issues": issues,
        "generated_sparql": report.get("generated_sparql"),
        "selected_predicates": [f.get("predicate") for f in fields if isinstance(f, dict)],
        "reason": None if grounded else "Expected one valid field in the requested domain, with no joins",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5-coder:3b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--max-shapes", type=int, default=10)
    ap.add_argument("--output", default="reports/v4_1_eight_query_pilot_results.json")
    ap.add_argument("--skip-execution", action="store_true")
    args = ap.parse_args()
    manifest = json.loads((ROOT / "experiments/benchmarks/v4_1_eight_query_pilot.json").read_text(encoding="utf-8"))
    schema = extract()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for case in manifest["cases"]:
        item = dict(case)
        issue = preflight(case, schema)
        if issue:
            item.update({"preflight_error": issue, "answer_correctness": "NOT_EVALUATED"})
        else:
            detail = output.parent / ("v4_1_pilot_" + case["id"] + ".json")
            cmd = [
                sys.executable, str(ROOT / "experiments/ontology_nl2sparql_generic_v4_1.py"),
                "--question", case["question"], "--model", args.model,
                "--ollama-url", args.ollama_url, "--graphdb-url", args.graphdb_url,
                "--max-shapes", str(args.max_shapes), "--output", str(detail),
            ]
            if args.skip_execution:
                cmd.append("--skip-execution")
            # The V4.1 script appends a timestamp if the output exists.
            # Remove only this dedicated pilot output to keep the path deterministic.
            if detail.exists():
                detail.unlink()
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            item["return_code"] = proc.returncode
            item["report_path"] = str(detail.relative_to(ROOT))
            item["stdout_tail"] = proc.stdout[-1000:]
            item["stderr_tail"] = proc.stderr[-1000:]
            if detail.exists():
                item.update(evaluate(case, json.loads(detail.read_text(encoding="utf-8"))))
            else:
                item["error"] = "V4.1 did not produce its report"
                item["answer_correctness"] = "NOT_EVALUATED"
        cases.append(item)
        print(case["id"], "grounding:", item.get("schema_grounding_pass"),
              "rows:", item.get("binding_count"), "error:", item.get("error") or item.get("preflight_error"), flush=True)
    summary = {
        "total": len(cases),
        "schema_grounding_pass": sum(x.get("schema_grounding_pass") is True for x in cases),
        "execution_success": sum(x.get("execution_success") is True for x in cases),
        "answer_correctness": "NOT_EVALUATED",
        "note": "No reference answer comparison; zero rows alone is not a failure. Not a measure of overall NL-to-SPARQL accuracy.",
    }
    output.write_text(json.dumps({"experiment": manifest["experiment"], "model": args.model,
                                  "summary": summary, "cases": cases}, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print("Saved:", output)
    return 0 if summary["schema_grounding_pass"] == len(cases) and (args.skip_execution or summary["execution_success"] == len(cases)) else 1


if __name__ == "__main__":
    sys.exit(main())
