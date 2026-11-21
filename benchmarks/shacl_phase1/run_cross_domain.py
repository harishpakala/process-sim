"""Cross-domain SHACL Phase-1 benchmark: semantic PASS/FAIL and elapsed times.

Run with: python -m benchmarks.shacl_phase1.run_cross_domain --scenario CD20
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.cross_domain_phase1 import run_cross_domain


def _candidate_path(cid, lookup):
    return lookup.get(cid, {}).get("path")


def _owner_property(cid, lookup):
    path = _candidate_path(cid, lookup)
    if not path:
        return None
    parts = [x.strip().casefold() for x in path.split(" → ")]
    return ".".join(parts[-2:]) if len(parts) >= 3 else None


def _entity(cid, lookup):
    path = _candidate_path(cid, lookup)
    if not path:
        return None
    parts = [x.strip().casefold() for x in path.split(" → ")]
    return parts[-1] if len(parts) >= 2 else None


def evaluate(record, expected):
    """Compare grounded semantics, not just the planner's validity flag."""
    errors = []
    if record.get("status") != "valid_response":
        errors.append("invalid_planner_status")
    if record.get("qwen_calls") != 1:
        errors.append("wrong_qwen_call_count")
    answer = record.get("answer") or {}
    lookup = {c["id"]: c for c in record.get("candidate_paths", [])}
    if sorted(record.get("domains") or []) != sorted(expected["domains"]):
        errors.append("domains")

    # Some valid plans represent the second matched entity as existence-only.
    projections = answer.get("projection_ids") or []
    existence = answer.get("existence_ids") or []
    actual_entities = sorted(_entity(cid, lookup) for cid in set(projections + existence))
    wanted_entities = sorted(x.split(".")[-1].casefold() for x in expected["projections"])
    if actual_entities != wanted_entities or not projections:
        errors.append("result_entities")
    if any(lookup.get(cid, {}).get("kind") != "result" for cid in projections + existence):
        errors.append("result_entity_paths")

    actual_filters = sorted(
        (_owner_property(f.get("property_id"), lookup),
         f.get("operator"), str(f.get("value")))
        for f in answer.get("filters", []) if isinstance(f, dict))
    wanted_filters = sorted(
        (f["property"].casefold(), f["operator"], str(f["value"]))
        for f in expected["filters"])
    if actual_filters != wanted_filters:
        errors.append("filters")
    if answer.get("boolean_operator") != expected["boolean_operator"]:
        errors.append("boolean_operator")
    if bool(answer.get("join")) != expected["join"]:
        errors.append("join")
    if answer.get("limit") != expected.get("limit"):
        errors.append("limit")

    actual_order = [
        (_owner_property(o.get("property_id"), lookup), o.get("direction"))
        for o in answer.get("order_by", []) if isinstance(o, dict)]
    order = expected.get("order_by")
    wanted_order = [(order["property"].casefold(), order["direction"])] if order else []
    if actual_order != wanted_order:
        errors.append("order_by")
    if answer.get("count_target_id") is not None:
        errors.append("unexpected_count")

    mapping_id = expected.get("mapping_id")
    actual_mappings = answer.get("mapping_ids") or []
    if actual_mappings != ([mapping_id] if mapping_id else []):
        errors.append("mapping_ids")
    approved = {
        m["id"]: m for m in record.get("mapping_candidates", [])
    }
    selected_mapping = approved.get(mapping_id)
    if mapping_id and selected_mapping is None:
        errors.append("mapping_not_offered")
    if selected_mapping:
        endpoints = set(answer.get("identifier_path_ids") or [])
        pairs = selected_mapping.get("join_alternatives") or []
        valid_pairs = [
            {p["left_id"], p["right_id"]} for p in pairs
        ]
        if endpoints not in valid_pairs:
            errors.append("identifier_endpoints")
        verified = record.get("validated_mappings") or []
        if not verified:
            errors.append("mapping_not_validated")
    if record.get("validation_errors"):
        errors.append("validation_errors")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["baseline", "robustness"], default="baseline")
    ap.add_argument("--benchmark", type=Path, help="Override suite manifest path")
    ap.add_argument("--schema", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json")
    ap.add_argument("--mappings", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/cross-domain-mappings.json")
    ap.add_argument("--scenario", help="e.g. CD20; omit to run all cross-domain scenarios")
    ap.add_argument("--retrieval", choices=["exact", "semantic", "expanded"], default="expanded")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--output", type=Path,
                    default=ROOT / "shacl_cross_domain_benchmark_results.json")
    args = ap.parse_args(argv)

    manifest = args.benchmark or ROOT / "benchmarks/shacl_phase1" / (
        "cross_domain_baseline_queries.json" if args.suite == "baseline"
        else "cross_domain_robustness_queries.json")
    if not manifest.is_file():
        ap.error(f"Benchmark manifest not found: {manifest}")
    benchmark = json.loads(manifest.read_text(encoding="utf-8"))
    scenarios = [s for s in benchmark["scenarios"] if s["scenario_id"].startswith("CD")]
    if args.scenario:
        scenarios = [s for s in scenarios if s["scenario_id"] == args.scenario]
        if not scenarios:
            ap.error("Unknown cross-domain scenario: " + args.scenario)
    print(f"SUITE: {args.suite} | manifest: {manifest} | scenarios: {len(scenarios)}", flush=True)
    cache = {}
    results = []
    started_all = time.perf_counter()
    print(f'{"ID":<12} {"RESULT":<8} {"TIME":>9} {"QWEN":>5}  ERRORS', flush=True)
    print("-" * 70, flush=True)
    for scenario in scenarios:
        expected = scenario["expected_semantics"]
        domains = expected["domains"]
        if len(domains) < 2:
            ap.error("Scenario is not cross-domain: " + scenario["scenario_id"])
        for domain in domains:
            if domain not in cache:
                cache[domain] = load_index(args.schema, domain=domain)
        indices = {domain: cache[domain] for domain in domains}
        for variant in scenario["paraphrases"]:
            started = time.perf_counter()
            try:
                record = run_cross_domain(
                    indices, variant["query"], mapping_file=args.mappings,
                    method=args.retrieval, model=args.model, endpoint=args.endpoint)
                errors = evaluate(record, expected)
            except Exception as exc:
                record = {"status": "exception", "error": f"{type(exc).__name__}: {exc}"}
                errors = ["exception"]
            elapsed = round(time.perf_counter() - started, 2)
            passed = not errors
            results.append({
                "id": variant["id"], "scenario_id": scenario["scenario_id"],
                "query": variant["query"], "pass": passed,
                "seconds": elapsed, "qwen_seconds": record.get("elapsed_seconds"),
                "qwen_calls": record.get("qwen_calls"),
                "errors": errors, "record": record,
            })
            print(f'{variant["id"]:<12} {"PASS" if passed else "FAIL":<8} '
                  f'{elapsed:>7.2f}s {str(record.get("qwen_calls", "-")):>5}  '
                  f'{",".join(errors)}', flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    passed = sum(x["pass"] for x in results)
    print("-" * 70, flush=True)
    print(f"TOTAL {passed}/{len(results)} PASS | {time.perf_counter()-started_all:.2f}s")
    print("Details:", args.output)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
