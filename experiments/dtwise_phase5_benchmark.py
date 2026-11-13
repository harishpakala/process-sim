#!/usr/bin/env python3
"""Reproducible Phase 5 benchmark. Never equate compilation with answer correctness.

Manifest case schema: id, question, expected_route (optional),
expected_engineering_ids (optional; exact set), expected_binding_count (optional).
Missing gold => semantic verdict NOT_EVALUATED. Runs router via subprocess to
preserve V4.1 behavior. For historical Q1-Q7, supply their real question/gold manifest.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dtwise_phase4_router import route
ROOT=Path(__file__).resolve().parents[1]
ROUTER=ROOT/"experiments/dtwise_phase4_router.py"
def evaluate(case,report,exit_code):
    expected_route=case.get("expected_route")
    actual_route=report.get("route") or ("generic_v4_1" if report.get("method")=="generic_v4_1_ontology_structural_validation" else None)
    executed=(report.get("status")=="executed" or
              (report.get("method")=="generic_v4_1_ontology_structural_validation" and report.get("graphdb_bindings") is not None and report.get("error") is None))
    compiled=bool(report.get("sparql") or report.get("generated_sparql"))
    bindings=report.get("results") if actual_route=="ebom_v2_catalog" else report.get("graphdb_bindings")
    if not isinstance(bindings,list):bindings=None
    verdict="NOT_EVALUATED"
    if "expected_engineering_ids" in case:
        if bindings is None:verdict="NOT_EVALUATED"
        else:
            actual=[b.get("engineeringId",{}).get("value") for b in bindings]
            verdict="PASS" if len(actual)==len(set(actual)) and set(actual)==set(case["expected_engineering_ids"]) else "FAIL"
    elif "expected_binding_count" in case:
        verdict="NOT_EVALUATED" if bindings is None else ("PASS" if len(bindings)==case["expected_binding_count"] else "FAIL")
    route_verdict="NOT_EVALUATED" if expected_route is None else ("PASS" if expected_route==actual_route else "FAIL")
    return {"id":case["id"],"question":case["question"],"route":actual_route,
            "route_verdict":route_verdict,"compiled":compiled,"executed":executed,
            "binding_count":len(bindings) if bindings is not None else None,
            "semantic_verdict":verdict,"return_code":exit_code,
            "error":report.get("error") or report.get("reason")}
def run(manifest,output,endpoint,skip_execution,model,timeout):
    cases=manifest["cases"]
    if not cases or len({c["id"] for c in cases})!=len(cases):raise ValueError("Empty or duplicate benchmark IDs")
    run_dir=output.parent/(output.stem+"_cases")
    run_dir.mkdir(parents=True,exist_ok=True)
    results=[]
    for index,case in enumerate(cases):
        if not isinstance(case.get("question"),str) or not case["question"].strip():raise ValueError("Missing question")
        path=run_dir/("case_"+str(index+1).zfill(3)+".json")
        cmd=[sys.executable,str(ROUTER),"--question",case["question"],"--graphdb-url",endpoint,"--output",str(path)]
        if skip_execution:cmd.append("--skip-execution")
        if model and route(case["question"])=="generic_v4_1":cmd.extend(["--model",model])
        start=time.monotonic()
        try:
            proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
            report=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            result=evaluate(case,report,proc.returncode)
            if not report:result["error"]="No audit report written; stderr: "+proc.stderr[-1200:]
        except subprocess.TimeoutExpired:
            result=evaluate(case,{},124)
            result["error"]="Timeout"
        result["elapsed_seconds"]=round(time.monotonic()-start,3)
        result["audit_file"]=str(path)
        results.append(result)
        print(case["id"],result["route"],result["semantic_verdict"],flush=True)
    summary={"total":len(results),"compiled":sum(x["compiled"] for x in results),
             "executed":sum(x["executed"] for x in results),
             "semantic_pass":sum(x["semantic_verdict"]=="PASS" for x in results),
             "semantic_fail":sum(x["semantic_verdict"]=="FAIL" for x in results),
             "semantic_not_evaluated":sum(x["semantic_verdict"]=="NOT_EVALUATED" for x in results),
             "route_pass":sum(x["route_verdict"]=="PASS" for x in results),
             "route_fail":sum(x["route_verdict"]=="FAIL" for x in results)}
    audit={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"summary":summary,
           "execution_skipped":skip_execution,"cases":results,
           "interpretation":"Semantic PASS requires supplied gold and executed bindings; compilation alone never counts."}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("Audit:",output)
    return audit
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=ROOT/"experiments/benchmarks/phase5_condenser_verified.json")
    p.add_argument("--output",type=Path,default=ROOT/"reports/phase5_benchmark.json")
    p.add_argument("--graphdb-url",default="http://localhost:7200/repositories/AAS")
    p.add_argument("--skip-execution",action="store_true")
    p.add_argument("--model")
    p.add_argument("--timeout",type=int,default=420)
    a=p.parse_args()
    audit=run(json.loads(a.manifest.read_text(encoding="utf-8")),a.output,a.graphdb_url,a.skip_execution,a.model,a.timeout)
    return 1 if audit["summary"]["semantic_fail"] or audit["summary"]["route_fail"] or any(c["return_code"] for c in audit["cases"]) else 0
if __name__=="__main__":sys.exit(main())
