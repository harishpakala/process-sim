"""Run all 100 questions from the supplied SHACL Phase-1 manifest.

Runs the single-domain (70) and cross-domain (30) evaluators separately.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=Path,
                    default=ROOT / "benchmarks/shacl_phase1/benchmark_queries.json")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "benchmark_results")
    ap.add_argument("--retrieval", choices=["exact", "semantic", "expanded"], default="expanded")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--schema", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json")
    ap.add_argument("--mappings", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/cross-domain-mappings.json")
    ap.add_argument("--generate-sparql", action="store_true",
                    help="Compile saved single-domain plans into SPARQL")
    ap.add_argument("--execute-graphdb", action="store_true",
                    help="Execute compiled SELECT queries (implies --generate-sparql)")
    ap.add_argument("--graphdb-endpoint", default="http://localhost:7200/repositories/AAST")
    ap.add_argument("--graphdb-timeout", type=float, default=60)
    ap.add_argument("--graph-mapping", type=Path,
                    help="Optional domain-to-named-graph JSON mapping")
    args = ap.parse_args(argv)
    if args.graphdb_timeout <= 0:
        ap.error("--graphdb-timeout must be positive")
    if args.graph_mapping and not args.execute_graphdb:
        ap.error("--graph-mapping requires --execute-graphdb")
    manifest = json.loads(args.benchmark.read_text(encoding="utf-8"))
    scenarios = manifest["scenarios"]
    ids = [v["id"] for s in scenarios for v in s["paraphrases"]]
    if len(scenarios) != 20 or len(ids) != 100 or len(set(ids)) != 100:
        ap.error("Expected 20 scenarios and 100 unique question IDs")
    if sum(len(s["paraphrases"]) for s in scenarios if s["scenario_id"].startswith("SD")) != 70:
        ap.error("Expected 70 single-domain questions")
    if sum(len(s["paraphrases"]) for s in scenarios if s["scenario_id"].startswith("CD")) != 30:
        ap.error("Expected 30 cross-domain questions")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    started = time.perf_counter()
    for label, module in [
        ("single_domain", "benchmarks.shacl_phase1.run_single_domain"),
        ("cross_domain", "benchmarks.shacl_phase1.run_cross_domain"),
    ]:
        output = args.output_dir / (label + ".json")
        cmd = [
            sys.executable, "-m", module, "--benchmark", str(args.benchmark),
            "--schema", str(args.schema), "--retrieval", args.retrieval,
            "--model", args.model, "--endpoint", args.endpoint,
            "--output", str(output),
        ]
        if label == "cross_domain":
            cmd += ["--mappings", str(args.mappings)]
        elif args.execute_graphdb:
            cmd += ["--execute-graphdb", "--graphdb-endpoint", args.graphdb_endpoint,
                    "--graphdb-timeout", str(args.graphdb_timeout),
                    "--sparql-output", str(args.output_dir / "single_domain_sparql_results.json"),
                    "--execution-output", str(args.output_dir / "single_domain_sparql_execution.json")]
            if args.graph_mapping:
                cmd += ["--graph-mapping", str(args.graph_mapping)]
        print(f"\\n=== {label} ===", flush=True)
        completed = subprocess.run(cmd, cwd=ROOT, check=False)
        if not output.is_file():
            print(f"Missing output from {label}: {output}", file=sys.stderr)
            return 2
        rows = json.loads(output.read_text(encoding="utf-8"))
        outputs[label] = {"pass": sum(bool(x["pass"]) for x in rows),
                          "total": len(rows), "exit_code": completed.returncode,
                          "file": str(output)}
    passed = sum(x["pass"] for x in outputs.values())
    total = sum(x["total"] for x in outputs.values())
    # Reuse existing compilation and read-only GraphDB execution tools.
    # Cross-domain SPARQL compilation is not supported by this pipeline.
    sparql_summary = {"scope": "single_domain", "eligible": 70,
                      "cross_domain": "not_supported"}
    if args.generate_sparql and not args.execute_graphdb:
        compiled_path = args.output_dir / "single_domain_sparql_results.json"
        cmd = [sys.executable, "-m",
               "benchmarks.shacl_phase1.run_single_domain_sparql",
               "--benchmark", str(args.benchmark), "--schema", str(args.schema),
               "--phase1-results", str(args.output_dir / "single_domain.json"),
               "--all-single-domain", "--output", str(compiled_path)]
        stage_started = time.perf_counter()
        compilation = subprocess.run(cmd, cwd=ROOT, check=False)
        sparql_summary["compilation_seconds"] = round(time.perf_counter() - stage_started, 3)
        sparql_summary["compilation_exit_code"] = compilation.returncode
        if compiled_path.is_file():
            compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
            counts = {}
            for item in compiled:
                status = item.get("status", "unknown")
                counts[status] = counts.get(status, 0) + 1
            sparql_summary["compilation_status_counts"] = counts
            sparql_summary["generated_queries"] = sum(
                item.get("status") == "compiled" and bool(item.get("sparql"))
                for item in compiled)
            sparql_summary["compilation_total"] = len(compiled)
        else:
            sparql_summary["compilation_error"] = "Compilation output missing"
        if args.execute_graphdb and compiled_path.is_file():
            execution_path = args.output_dir / "single_domain_sparql_execution.json"
            cmd = [sys.executable, "-m",
                   "benchmarks.shacl_phase1.execute_single_domain_sparql",
                   "--input", str(compiled_path), "--output", str(execution_path),
                   "--endpoint", args.graphdb_endpoint,
                   "--timeout", str(args.graphdb_timeout)]
            if args.graph_mapping:
                cmd += ["--graph-mapping", str(args.graph_mapping)]
            stage_started = time.perf_counter()
            execution = subprocess.run(cmd, cwd=ROOT, check=False)
            sparql_summary["execution_seconds"] = round(time.perf_counter() - stage_started, 3)
            sparql_summary["execution_exit_code"] = execution.returncode
            if execution_path.is_file():
                executed = json.loads(execution_path.read_text(encoding="utf-8"))
                counts = {}
                for item in executed:
                    status = item.get("status", "unknown")
                    counts[status] = counts.get(status, 0) + 1
                sparql_summary["execution_status_counts"] = counts
                sparql_summary["executed_queries"] = sum(
                    item.get("status") in ("executed_with_results", "executed_zero_rows")
                    for item in executed)
                sparql_summary["total_result_rows"] = sum(
                    item.get("row_count") or 0 for item in executed)
                sparql_summary["execution_total"] = len(executed)
                sparql_summary["semantic_correctness"] = "not_checked"
            else:
                sparql_summary["execution_error"] = "Execution output missing"
    if args.execute_graphdb:
        compiled_path = args.output_dir / "single_domain_sparql_results.json"
        execution_path = args.output_dir / "single_domain_sparql_execution.json"
        if compiled_path.is_file() and execution_path.is_file():
            compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
            executed = json.loads(execution_path.read_text(encoding="utf-8"))
            compilation_counts = {}
            execution_counts = {}
            for item in compiled:
                status = item.get("status", "unknown")
                compilation_counts[status] = compilation_counts.get(status, 0) + 1
            for item in executed:
                status = item.get("status", "unknown")
                execution_counts[status] = execution_counts.get(status, 0) + 1
            sparql_summary.update({
                "compilation_status_counts": compilation_counts,
                "compilation_total": len(compiled),
                "generated_queries": sum(bool(x.get("sparql")) and x.get("status") == "compiled" for x in compiled),
                "execution_status_counts": execution_counts,
                "execution_total": len(executed),
                "executed_queries": sum(x.get("status") in ("executed_with_results", "executed_zero_rows") for x in executed),
                "total_result_rows": sum(x.get("row_count") or 0 for x in executed),
                "semantic_correctness": "not_checked",
                "compilation_exit_code": 0 if len(compiled) == 70 and all(x.get("status") == "compiled" for x in compiled) else 1,
                "execution_exit_code": 0 if len(executed) == 70 and all(x.get("status") in ("executed_with_results", "executed_zero_rows") for x in executed) else 1,
            })
        else:
            sparql_summary["error"] = "Missing live compilation or execution output"
    summary = {"benchmark": str(args.benchmark), "pass": passed, "total": total,
               "seconds": round(time.perf_counter() - started, 2), "suites": outputs}
    if args.generate_sparql or args.execute_graphdb:
        summary["sparql"] = sparql_summary
    if False and args.execute_graphdb and "execution_status_counts" in sparql_summary:
        planner_rows = {}
        for label in ("single_domain", "cross_domain"):
            path = args.output_dir / (label + ".json")
            for item in json.loads(path.read_text(encoding="utf-8")):
                planner_rows[item["id"]] = item
        execution_path = args.output_dir / "single_domain_sparql_execution.json"
        execution_rows = json.loads(execution_path.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in execution_rows}
        print("\\n=== Single-domain planner and GraphDB results ===", flush=True)
        print(f'{"ID":<12} {"RESULT":<8} {"TIME":>9} {"ROWS":>8}  GRAPHDB', flush=True)
        print("-" * 62, flush=True)
        for question_id, item in planner_rows.items():
            if not question_id.startswith("SD"):
                continue
            execution = by_id.get(question_id, {})
            count = execution.get("row_count")
            rows_text = str(count) if count is not None else "-"
            status = execution.get("status", "not_executed")
            print(f'{question_id:<12} {"PASS" if item.get("pass") else "FAIL":<8} '
                  f'{item.get("seconds", 0):>7.2f}s {rows_text:>8}  {status}',
                  flush=True)
        print("ROWS = GraphDB result bindings; '-' = no successful execution.", flush=True)
        print("Planner PASS does not establish GraphDB semantic correctness.", flush=True)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\\nTOTAL {passed}/{total} PASS | {summary['seconds']:.2f}s", flush=True)
    print(f"Summary: {summary_path}", flush=True)
    planner_ok = total == 100 and passed == 100 and all(
        x["exit_code"] == 0 for x in outputs.values())
    sparql_ok = (not (args.generate_sparql or args.execute_graphdb) or
                 (sparql_summary.get("compilation_exit_code") == 0 and
                  (not args.execute_graphdb or
                   sparql_summary.get("execution_exit_code") == 0)))
    return 0 if planner_ok and sparql_ok else 1


if __name__ == "__main__":
    sys.exit(main())
