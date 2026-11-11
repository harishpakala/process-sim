#!/usr/bin/env python3
"""Run 15 held-out questions against frozen generic v3; score structural evidence only.

The benchmark expectations never enter the NL-to-SPARQL prompt. GraphDB rows are
diagnostic, not proof of semantic correctness. Manually review generated queries.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).with_name("ontology_nl2sparql_blind15.json")
SCRIPT = Path(__file__).with_name("ontology_nl2sparql_generic_v3.py")

def local(uri):
    return str(uri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]

def score(case, audit, returncode):
    issues = []
    if returncode != 0:
        issues.append("process_exit_nonzero")
    if not audit:
        return {"status": "error", "issues": ["missing_or_unreadable_audit"]}
    if audit.get("error"):
        issues.append("runtime_error: " + str(audit["error"]))
    if audit.get("plan_issues"):
        issues.append("plan_rejected: " + str(audit["plan_issues"]))
    plan = audit.get("plan") or {}
    fields = plan.get("fields") or []
    cat = audit.get("candidate_shapes") or {}
    selected = [f for f in fields if isinstance(f, dict)]
    actual = {local(f.get("predicate", "")) for f in selected}
    missing = set(case["required_output_predicate_local_names"]) - actual
    if missing:
        issues.append("missing_output_predicates: " + ", ".join(sorted(missing)))
    used = {cat.get(f.get("shape"), {}).get("domain") for f in selected}
    used.update(cat.get(f.get("shape"), {}).get("domain") for f in (plan.get("filters") or []) if isinstance(f, dict))
    joined = set(audit.get("joined_shapes") or [])
    joined_domains = {cat.get(s, {}).get("domain") for s in joined}
    missing_domains = set(case["required_domains"]) - joined_domains
    if missing_domains:
        issues.append("missing_joined_domains: " + ", ".join(sorted(missing_domains)))
    selected_joins = audit.get("selected_joins") or []
    if len(selected_joins) != case["min_joins"]:
        issues.append("join_count_expected_%s_got_%s" % (case["min_joins"], len(selected_joins)))
    if case["expectation"] == "unsupported":
        # The v3 validator does not yet reject nonempty unsupported lists;
        # a compiled query omitting the unsupported output is a failure.
        if audit.get("generated_sparql"):
            issues.append("unsupported_request_compiled_query")
        status = "correct_abstention" if not audit.get("generated_sparql") and (plan.get("unsupported") or audit.get("plan_issues")) else "failed_abstention"
    else:
        if not audit.get("generated_sparql"):
            issues.append("no_compiled_query")
        status = "structural_pass" if not issues else "structural_fail"
    return {"status": status, "issues": issues,
            "binding_count": audit.get("binding_count"),
            "selected_joins": selected_joins,
            "output_predicates": sorted(actual),
            "used_field_domains": sorted(x for x in used if x),
            "joined_domains": sorted(x for x in joined_domains if x),
            "elapsed_seconds": audit.get("elapsed_seconds")}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5-coder:3b")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=1000)
    ap.add_argument("--max-prompt-estimate", type=int, default=5000)
    ap.add_argument("--max-shapes", type=int, default=10)
    ap.add_argument("--ollama-timeout", type=int, default=300)
    ap.add_argument("--skip-execution", action="store_true")
    ap.add_argument("--ids", nargs="*", help="Optional IDs, e.g. B01 B07 B14")
    ap.add_argument("--output-dir", default="reports/blind15_v3")
    args = ap.parse_args()
    suite = json.loads(CASES.read_text(encoding="utf-8"))
    selected = [c for c in suite["cases"] if not args.ids or c["id"] in args.ids]
    if args.ids and set(args.ids) - {c["id"] for c in selected}:
        ap.error("Unknown case IDs: " + ", ".join(sorted(set(args.ids) - {c["id"] for c in selected})))
    out = Path(args.output_dir)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for case in selected:
        audit_path = out / (case["id"] + "_audit.json")
        # A fresh file avoids v3's automatic timestamped filename behavior.
        if audit_path.exists():
            audit_path = out / (case["id"] + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_audit.json")
        cmd = [sys.executable, str(SCRIPT), "--question", case["question"],
               "--model", args.model, "--num-ctx", str(args.num_ctx),
               "--num-predict", str(args.num_predict),
               "--max-prompt-estimate", str(args.max_prompt_estimate),
               "--max-shapes", str(args.max_shapes),
               "--ollama-timeout", str(args.ollama_timeout),
               "--output", str(audit_path)]
        if args.skip_execution:
            cmd.append("--skip-execution")
        print("\n=== %s / %s ===\n%s" % (case["id"], case["category"], case["question"]), flush=True)
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), check=False, timeout=args.ollama_timeout + 150)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = 124
            print("Timed out", flush=True)
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            audit = None
        assessment = score(case, audit, rc)
        result = {"id": case["id"], "category": case["category"],
                  "question": case["question"], "expectation": case["expectation"],
                  "audit_file": str(audit_path), **assessment}
        results.append(result)
        print("ASSESSMENT:", assessment["status"], assessment["issues"], flush=True)
        summary = {"benchmark_id": suite["benchmark_id"], "model": args.model,
                   "v3_script": str(SCRIPT), "results": results,
                   "counts": {s: sum(x["status"] == s for x in results)
                              for s in ("structural_pass", "structural_fail", "correct_abstention", "failed_abstention", "error")},
                   "note": "Structural checks are necessary but not sufficient for semantic correctness. Manually inspect filters, shapes, joins, and bindings."}
        (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nSummary:", out / "summary.json")
    return 0 if all(r["status"] in ("structural_pass", "correct_abstention") for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
