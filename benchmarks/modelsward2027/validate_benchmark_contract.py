"""Offline metadata gate; not a SPARQL semantic validator."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8-sig"))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--require-freeze", action="store_true")
    args = p.parse_args()
    m = load("benchmark_queries_modelsward2027.json")
    refs = load("reference_queries_modelsward2027.json")["references"]
    gold = load("reference_validation_results.json")
    audit = load("scenario_audit.json")
    errors, pending = [], []
    def check(ok, msg):
        if not ok:
            errors.append(msg)
    def index(rows, key):
        out = {}
        for row in rows:
            k = row[key]
            check(k not in out, "duplicate "+key+": "+k)
            out[k] = row
        return out
    scenarios = index(m["scenarios"], "scenario_id")
    r = index(refs, "scenario_id")
    g = index(gold["results"], "scenario_id")
    a = index(audit["scenarios"], "scenario_id")
    index(refs, "reference_query_id")
    check(len(scenarios)==m["scenario_count"]==46, "scenario count")
    questions = [q for s in scenarios.values() for q in s["paraphrases"]]
    index(questions, "id")
    check(len(questions)==m["query_count"]==230, "question count")
    check(set(a)==set(scenarios), "audit coverage")
    supported = {k for k,s in scenarios.items() if s["expected_behavior"]!="reject"}
    check(set(r)==set(g)==supported, "reference coverage")
    check(hashlib.sha256((HERE/"reference_queries_modelsward2027.json").read_bytes()).hexdigest()==gold["reference_sha256"], "reference hash mismatch")
    check(gold["inference_requested"] is False, "inference setting")
    for k,s in scenarios.items():
        sem = s["expected_semantics"]
        check(len(s["paraphrases"])==5, k+": paraphrase count")
        check(all(q["query"].strip() for q in s["paraphrases"]), k+": empty question")
        if k in a:
            item=a[k]
            if item["review_status"]!="approved" or not item.get("reviewer") or not item.get("review_evidence"):
                pending.append(k)
        if s["expected_behavior"]=="reject":
            check(bool(sem.get("expected_rejection")), k+": missing rejection reason")
            check(not s.get("reference_query_id"), k+": negative reference")
            continue
        if k not in r or k not in g:
            continue
        ref, result = r[k],g[k]
        check(s["reference_query_id"]==ref["reference_query_id"]==result["reference_query_id"], k+": reference ID")
        check(sem["projections"]==ref["projection_roles"], k+": projection metadata")
        check(len(result["variables"])==len(ref["projection_roles"]), k+": projection arity")
        check(len(set(result["variables"]))==len(result["variables"]), k+": duplicate variables")
        check(result["row_count"]==len(result["bindings"]), k+": row count")
        check(result["status"]=="pass", k+": recorded execution status")
        check(ref["expected_empty"]==(s["expected_behavior"]=="execute_empty"), k+": empty contract")
        check((result["row_count"]==0)==ref["expected_empty"], k+": recorded emptiness")
        check(bool(sem.get("order_by"))==ref["ordered"], k+": ordering metadata")
        for row in result["bindings"]:
            check(set(row)<=set(result["variables"]), k+": unknown binding variable")
            check(all(isinstance(v,dict) and "type" in v and "value" in v for v in row.values()), k+": malformed RDF term")
    print(json.dumps({"metadata_errors":errors,"pending_semantic_review":pending,
                      "scenario_count":len(scenarios),"question_count":len(questions),
                      "freeze_ready":False,
                      "note":"Offline checks only; live snapshot and independent semantic approval required."},indent=2))
    # This draft cannot authorize a freeze even if all metadata checks pass.
    return 1 if errors or args.require_freeze else 0

if __name__=="__main__":
    raise SystemExit(main())
