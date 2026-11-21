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
    args = ap.parse_args(argv)
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
    summary = {"benchmark": str(args.benchmark), "pass": passed, "total": total,
               "seconds": round(time.perf_counter() - started, 2), "suites": outputs}
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\\nTOTAL {passed}/{total} PASS | {summary['seconds']:.2f}s", flush=True)
    print(f"Summary: {summary_path}", flush=True)
    return 0 if total == 100 and passed == 100 and all(
        x["exit_code"] == 0 for x in outputs.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
