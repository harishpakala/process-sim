"""Compile validated single-domain Phase-1 benchmark records to SPARQL.

By default, reuse existing Phase-1 results (zero Ollama calls). An explicit
--run-planner flag runs Phase 1 when no input results are supplied.
This runner does not execute SPARQL against a triplestore.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.legacy_candidate_recovery import (
    RecoveryError, recover_registry,
)
from process_sim.dtwise.shacl_planner.sparql_compiler import (
    CompilationError, compile_single_domain,
)


def _manifest(path, scenarios):
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for scenario in data["scenarios"]:
        sid = scenario["scenario_id"]
        if not sid.startswith("SD") or (scenarios and sid not in scenarios):
            continue
        domains = scenario["expected_semantics"]["domains"]
        if len(domains) != 1:
            raise ValueError("Expected one domain for " + sid)
        for variant in scenario["paraphrases"]:
            entries.append({
                "id": variant["id"], "scenario_id": sid,
                "query": variant["query"], "domain": domains[0],
                "expected_semantics": scenario["expected_semantics"],
            })
    if scenarios - {e["scenario_id"] for e in entries}:
        raise ValueError("Unknown scenarios: " + ", ".join(sorted(
            scenarios - {e["scenario_id"] for e in entries})))
    return entries


def _existing(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    # run_single_domain.py produces a list; run_all.py may wrap it.
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            data = data["results"]
        else:
            raise ValueError("Expected a list of single-domain results")
    if not isinstance(data, list):
        raise ValueError("Expected a list of single-domain results")
    result = {}
    for item in data:
        key = item.get("id")
        if not isinstance(key, str) or key in result:
            raise ValueError("Missing or duplicate result ID: " + str(key))
        result[key] = item
    return result


def compile_entry(entry, prior, index, schema):
    """Classify semantic failures separately from compiler failures."""
    base = {
        "id": entry["id"], "scenario_id": entry["scenario_id"],
        "domain": entry["domain"], "query": entry["query"],
        "sparql": None, "error": None,
    }
    if prior is None:
        return {**base, "status": "missing_phase1_result",
                "error": "No Phase-1 result for this question"}
    if prior.get("query") != entry["query"]:
        return {**base, "status": "input_mismatch",
                "error": "Phase-1 question text differs from benchmark manifest"}
    record = prior.get("record")
    if not isinstance(record, dict):
        return {**base, "status": "invalid_phase1_record",
                "error": "Phase-1 record is missing"}
    if record.get("status") != "valid_response" or record.get("validation_errors"):
        return {**base, "status": "planning_failed",
                "error": record.get("validation_errors") or record.get("error") or
                         record.get("status")}
    # Preserve the existing benchmark's semantic pass/fail result. Do not
    # interpret a valid_response as proof of correct NL interpretation.
    if prior.get("pass") is False:
        return {**base, "status": "semantic_mismatch",
                "error": prior.get("errors") or "Phase-1 benchmark failed"}
    if not record.get("candidate_registry"):
        try:
            recovered = recover_registry(record, index)
        except RecoveryError as exc:
            return {**base, "status": "registry_recovery_failed", "error": str(exc)}
        record = {**record, "candidate_registry": recovered}
    try:
        sparql = compile_single_domain(record, index, schema)
    except CompilationError as exc:
        return {**base, "status": "compilation_failed", "error": str(exc)}
    except (KeyError, TypeError, ValueError) as exc:
        return {**base, "status": "compiler_error",
                "error": f"{type(exc).__name__}: {exc}"}
    return {**base, "status": "compiled", "sparql": sparql}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", type=Path,
                    default=ROOT / "benchmarks/shacl_phase1/benchmark_queries.json")
    ap.add_argument("--schema", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json")
    ap.add_argument("--phase1-results", type=Path,
                    help="Existing run_single_domain.py JSON output; no Ollama calls")
    ap.add_argument("--run-planner", action="store_true",
                    help="Explicitly run Phase 1 using local Ollama")
    ap.add_argument("--scenario", action="append",
                    help="Repeatable scenario selector, e.g. SD01 (default SD01–SD06)")
    ap.add_argument("--all-single-domain", action="store_true",
                    help="Use all SD scenarios rather than default SD01–SD06")
    ap.add_argument("--retrieval", choices=("exact", "semantic", "expanded"),
                    default="expanded")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--output", type=Path,
                    default=ROOT / "benchmark_results/single_domain_sparql_results.json")
    args = ap.parse_args(argv)
    if bool(args.phase1_results) == bool(args.run_planner):
        ap.error("Specify exactly one of --phase1-results or --run-planner")
    if args.all_single_domain and args.scenario:
        ap.error("Use either --all-single-domain or --scenario")
    selected = set(args.scenario or ([] if args.all_single_domain else
                                     [f"SD{i:02d}" for i in range(1, 7)]))
    entries = _manifest(args.benchmark, selected)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    indices = {domain: load_index(args.schema, domain=domain)
               for domain in {e["domain"] for e in entries}}
    if args.phase1_results:
        previous = _existing(args.phase1_results)
    else:
        from benchmarks.shacl_phase1.run_single_domain import evaluate
        from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one
        previous = {}
    results = []
    for entry in entries:
        prior = previous.get(entry["id"])
        if args.run_planner:
            try:
                record = run_one(indices[entry["domain"]], entry["query"],
                                 method=args.retrieval, model=args.model,
                                 endpoint=args.endpoint)
                errors = evaluate(record, entry["expected_semantics"])
                prior = {"id": entry["id"], "query": entry["query"],
                         "pass": not errors, "errors": errors, "record": record}
            except Exception as exc:
                prior = {"id": entry["id"], "query": entry["query"], "pass": False,
                         "errors": ["exception"], "record": {
                             "status": "exception",
                             "error": f"{type(exc).__name__}: {exc}"}}
        result = compile_entry(entry, prior, indices[entry["domain"]], schema)
        results.append(result)
        print(f"{entry['id']:<12} {result['status']}", flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    counts = Counter(item["status"] for item in results)
    print("Summary:", dict(sorted(counts.items())))
    print("Output:", args.output)
    return 0 if counts.get("compiled", 0) == len(entries) else 1


if __name__ == "__main__":
    sys.exit(main())
