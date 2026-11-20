"""Run single-domain SHACL paraphrase benchmark; print PASS/FAIL and wall time."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one


def evaluate(record, expected):
    errors = []
    if record.get("status") != "valid_response":
        errors.append("invalid_planner_status")
    # Single-domain run_one does not expose qwen_calls. A present value is
    # checked, but an absent field is not evidence of a wrong call count.
    if "qwen_calls" in record and record["qwen_calls"] != 1:
        errors.append("wrong_qwen_call_count")
    answer = record.get("answer") or {}
    candidates = {c["id"]: c for c in record.get("candidate_paths", [])}

    def name(cid):
        c = candidates.get(cid)
        return c.get("path", "").split(" → ")[-1].casefold() if c else "<unknown>"

    actual = sorted(name(cid) for cid in answer.get("projection_ids", []))
    wanted = sorted(x.split(".")[-1].casefold() for x in expected["projections"])
    if actual != wanted:
        errors.append("projections")
    actual_filters = sorted((name(f.get("property_id")), f.get("operator"), str(f.get("value")))
                            for f in answer.get("filters", []))
    wanted_filters = sorted((f["property"].split(".")[-1].casefold(), f["operator"], str(f["value"]))
                            for f in expected["filters"])
    if actual_filters != wanted_filters:
        errors.append("filters")
    if answer.get("boolean_operator") != expected["boolean_operator"]:
        errors.append("boolean_operator")
    if bool(answer.get("join")) != expected["join"]:
        errors.append("join")
    actual_order = [(name(o.get("property_id")), o.get("direction")) for o in answer.get("order_by", [])]
    order = expected.get("order_by")
    wanted_order = [(order["property"].split(".")[-1].casefold(), order["direction"])] if order else []
    if actual_order != wanted_order:
        errors.append("order_by")
    if answer.get("limit") != expected.get("limit"):
        errors.append("limit")
    if answer.get("count_target_id") is not None:
        errors.append("unexpected_count")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=Path, default=ROOT / "benchmarks/shacl_phase1/benchmark_queries.json")
    ap.add_argument("--schema", type=Path, default=ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json")
    ap.add_argument("--scenario", help="e.g. SD01; omit for all single-domain scenarios")
    ap.add_argument("--retrieval", choices=["exact", "semantic", "expanded"], default="expanded")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--output", type=Path, default=ROOT / "shacl_single_domain_benchmark_results.json")
    args = ap.parse_args()
    scenarios = [s for s in json.loads(args.benchmark.read_text(encoding="utf-8"))["scenarios"]
                 if s["scenario_id"].startswith("SD")]
    if args.scenario:
        scenarios = [s for s in scenarios if s["scenario_id"] == args.scenario]
        if not scenarios:
            ap.error("Unknown single-domain scenario")
    cache = {}
    results = []
    started_all = time.perf_counter()
    print(f'{"ID":<12} {"RESULT":<8} {"TIME":>9}', flush=True)
    print("-" * 32, flush=True)
    for scenario in scenarios:
        expected = scenario["expected_semantics"]
        domains = expected["domains"]
        if len(domains) != 1:
            ap.error("Scenario is not single-domain: " + scenario["scenario_id"])
        domain = domains[0]
        if domain not in cache:
            cache[domain] = load_index(args.schema, domain=domain)
        for variant in scenario["paraphrases"]:
            started = time.perf_counter()
            try:
                record = run_one(cache[domain], variant["query"], method=args.retrieval,
                                 model=args.model, endpoint=args.endpoint)
                errors = evaluate(record, expected)
            except Exception as exc:
                record = {"status": "exception", "error": f"{type(exc).__name__}: {exc}"}
                errors = ["exception"]
            elapsed = round(time.perf_counter() - started, 2)
            passed = not errors
            results.append({"id": variant["id"], "query": variant["query"],
                            "pass": passed, "seconds": elapsed, "errors": errors, "record": record})
            print(f'{variant["id"]:<12} {"PASS" if passed else "FAIL":<8} {elapsed:>7.2f}s', flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(x["pass"] for x in results)
    print("-" * 32)
    print(f"TOTAL {passed}/{len(results)} PASS | {time.perf_counter()-started_all:.2f}s")
    print("Details:", args.output)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
