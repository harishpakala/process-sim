"""Experiment 35 staged benchmark: fresh retrieval, constrained SPARQL, and VTKG.

Run from repository root. Default runs 12 ontology questions; VTKG is opt-in.
  python experiments/vector_graph_rag/35_run_benchmark.py --stage ontology
  python experiments/vector_graph_rag/35_run_benchmark.py --stage ontology --no-execute
  python experiments/vector_graph_rag/35_run_benchmark.py --stage explicit --run-id UUID
  python experiments/vector_graph_rag/35_run_benchmark.py --stage all --run-id UUID

Explicit-function stage uses the existing deterministic VTKG CLI, not Experiment 34,
which is not committed on this branch. Implicit-function and safety cases are
recorded as not_evaluated until an evidence-based resolver and a contract runner
exist; they are NEVER counted as successes. No gold data enters prompts.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def load_module(name, filename):
    spec = spec_from_file_location(name, HERE / filename)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

def ontology_stage(args, cases, report):
    exp30 = load_module("e35_30", "30_evaluate_simple_questions.py")
    exp32 = load_module("e35_32", "32_execute_simple_sparql.py")
    exp33 = load_module("e35_33", "33_llm_sparql.py")
    index = read(args.index)
    concepts = sorted((c for c in index["concepts"]
                       if c.get("kind") == "property" and c.get("uri")),
                      key=lambda c: c["uri"])
    uris = [c["uri"] for c in concepts]
    if len(set(uris)) != len(uris):
        raise ValueError("Duplicate ontology property URI")
    by_uri = {c["uri"]: c for c in concepts}
    for c in cases:
        uri = c["gold"]["predicate_uri"]
        if uri not in by_uri or by_uri[uri]["domain"] != c["gold"]["domain"]:
            raise ValueError("Benchmark/index mismatch: " + c["id"])
    sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    cache = args.output.with_name("engineering_35_embedding_cache.json")
    cached = read(cache) if cache.exists() else {}
    if (cached.get("index_sha256") == sha and
        cached.get("model") == args.embedding_model and cached.get("uris") == uris):
        vectors = cached["vectors"]
    else:
        print("Embedding ontology properties...", flush=True)
        vectors = exp30.embed(args.ollama_url, args.embedding_model,
                              [exp30.concept_text(c) for c in concepts], args.timeout)
        save(cache, {"index_sha256": sha, "model": args.embedding_model,
                     "uris": uris, "vectors": vectors})
    for case in cases:
        start = time.monotonic()
        row = {"id": case["id"], "category": case["category"],
               "question": case["question"], "status": "error"}
        try:
            question = case["question"]
            lexical = exp30.lexical_ranking(question, concepts)
            qvec = exp30.embed(args.ollama_url, args.embedding_model,
                               [question], args.timeout)[0]
            vector = exp30.vector_ranking(qvec, vectors, concepts)
            hybrid = exp30.fusion(lexical, vector, concepts, args.vector_weight)
            rankings = {"lexical": lexical, "vector": vector, "hybrid": hybrid}
            gold = case["gold"]["predicate_uri"]
            row["retrieval"] = {}
            for method, order in rankings.items():
                top = [uris[i] for i in order[:args.top_k]]
                rank = next((n for n, i in enumerate(order, 1) if uris[i] == gold), None)
                row["retrieval"][method] = {
                    "top_uris": top, "gold_rank": rank,
                    "recall_at_1": rank == 1,
                    "recall_at_5": rank is not None and rank <= 5,
                    "domain_at_1_correct": by_uri[top[0]]["domain"] == case["gold"]["domain"]}
            row["status"] = "retrieved"
            if case["category"] == "predicate_sparql":
                candidates = row["retrieval"][args.method]["top_uris"]
                prompt = ("Generate exactly one read-only SPARQL SELECT query. "
                          "Use ONLY one candidate predicate. Use one triple "
                          "?subject <URI> ?value . No joins, FILTER, SERVICE, "
                          "GRAPH, OPTIONAL or other clauses. Output only SPARQL.\n"
                          "Question: " + question + "\nCandidate predicates:\n" +
                          "\n".join(f"{i}. {u}" for i, u in enumerate(candidates, 1)) +
                          "\nReturn SELECT DISTINCT ?subject ?value WHERE "
                          "{ ?subject <URI> ?value . } LIMIT 100")
                raw = exp33.ollama(args.ollama_url, args.model, prompt, args.timeout)
                uri, query = exp33.validate(exp33.clean(raw), set(by_uri), set(candidates))
                row["sparql"] = {"predicate": uri, "query": query,
                                 "predicate_correct": uri == gold,
                                 "domain_correct": by_uri[uri]["domain"] == case["gold"]["domain"],
                                 "validation": "ok"}
                if not args.no_execute:
                    bindings = exp32.execute(args.endpoint, query, args.timeout)
                    row["sparql"].update({"execution": "ok", "rows": len(bindings),
                                          "nonempty": bool(bindings),
                                          "sample_bindings": bindings[:2]})
                else:
                    row["sparql"]["execution"] = "not_executed"
                row["status"] = "ok"
            else:
                row["status"] = "ok"
        except Exception as exc:
            row["status"] = "error"
            row["error"] = str(exc)[:500]
        row["seconds"] = round(time.monotonic() - start, 2)
        report["results"].append(row)
        save(args.output, report)
        print(case["id"], row["status"], f"{row['seconds']}s", flush=True)

def explicit_stage(args, cases, report):
    if not args.run_id:
        raise ValueError("--run-id required for explicit VTKG stage")
    script = ROOT / "scripts" / "tep_nexus_live_virtual_graph.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    for case in cases:
        start = time.monotonic()
        function = case["gold"]["function"]
        result_path = args.output.parent / "engineering_35_vtkg" / (case["id"] + ".json")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(script), "--function", function,
                   "--run-id", args.run_id, "--start-seconds", str(args.start_seconds),
                   "--end-seconds", str(args.end_seconds),
                   "--limit", str(args.limit), "--output", str(result_path)]
        row = {"id": case["id"], "category": case["category"],
               "question": case["question"], "function": function,
               "expected_provisional_signal": case["gold"]["provisional_signal"]}
        try:
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                  timeout=args.timeout, check=False)
            row["returncode"] = proc.returncode
            if proc.returncode != 0:
                row.update({"status": "error", "error": proc.stderr[-1000:]})
            else:
                graph = read(result_path)
                result = graph.get("result", {})
                row.update({"status": "executed", "observation_count": result.get("observationCount"),
                            "truncated": result.get("truncated"),
                            "output": str(result_path)})
                # A successful deterministic run is NOT LLM function-selection
                # accuracy and is NOT baseline observation equivalence.
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)[:500]})
        row["seconds"] = round(time.monotonic() - start, 2)
        report["results"].append(row)
        save(args.output, report)
        print(case["id"], row["status"], flush=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["ontology", "explicit", "all"], default="ontology")
    ap.add_argument("--benchmark", type=Path, default=HERE / "data/engineering_questions_35.json")
    ap.add_argument("--index", type=Path, default=ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json")
    ap.add_argument("--output", type=Path, default=HERE / "data/engineering_benchmark_35_results.json")
    ap.add_argument("--method", choices=["lexical", "vector", "hybrid"], default="hybrid")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--no-execute", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--start-seconds", type=float, default=0)
    ap.add_argument("--end-seconds", type=float, default=60)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()
    if not 1 <= args.top_k <= 10 or not 0 <= args.vector_weight <= 1:
        ap.error("top-k must be 1..10 and vector-weight 0..1")
    if args.timeout <= 0 or args.limit < 1 or args.start_seconds < 0 or args.end_seconds < args.start_seconds:
        ap.error("Invalid timeout, limit or temporal interval")
    if args.stage in ("explicit", "all") and not args.run_id:
        ap.error("--run-id required for explicit or all stages")
    benchmark = read(args.benchmark)
    cases = benchmark["cases"]
    report = {"experiment": "35_extended_engineering_qa_benchmark",
              "status": "partial_staged_evaluation",
              "benchmark_sha256": hashlib.sha256(args.benchmark.read_bytes()).hexdigest(),
              "stage": args.stage, "method": args.method,
              "model": args.model, "embedding_model": args.embedding_model,
              "results": [], "not_evaluated": [],
              "limitations": [
                  "Curated, not held-out questions; some overlap prior tests.",
                  "Only single-predicate SPARQL validated; no joins.",
                  "Explicit VTKG runs test deterministic execution, not LLM entity resolution.",
                  "Implicit resolution and safety abstention require a dedicated evidence-based runner.",
                  "Nonempty SPARQL output is not answer correctness."]}
    if args.stage in ("ontology", "all"):
        ontology_stage(args, [c for c in cases if c["category"] in
                       ("concept_retrieval", "predicate_sparql")], report)
    if args.stage in ("explicit", "all"):
        explicit_stage(args, [c for c in cases if c["category"] == "explicit_function"], report)
    for case in cases:
        if not any(r["id"] == case["id"] for r in report["results"]):
            report["not_evaluated"].append({"id": case["id"], "category": case["category"],
                                             "reason": "stage_not_selected_or_not_implemented"})
    summary = {}
    for category in ("concept_retrieval", "predicate_sparql", "explicit_function"):
        rows = [r for r in report["results"] if r["category"] == category]
        if rows:
            s = {"evaluated": len(rows), "successful": sum(r["status"] in ("ok", "executed") for r in rows)}
            if category in ("concept_retrieval", "predicate_sparql"):
                s["retrieval"] = {method: {
                    "recall_at_1": sum(r.get("retrieval", {}).get(method, {}).get("recall_at_1", False) for r in rows),
                    "recall_at_5": sum(r.get("retrieval", {}).get(method, {}).get("recall_at_5", False) for r in rows),
                    "domain_at_1": sum(r.get("retrieval", {}).get(method, {}).get("domain_at_1_correct", False) for r in rows)
                } for method in ("lexical", "vector", "hybrid")}
            if category == "predicate_sparql":
                s["validated_queries"] = sum(r.get("sparql", {}).get("validation") == "ok" for r in rows)
                s["correct_predicates"] = sum(r.get("sparql", {}).get("predicate_correct", False) for r in rows)
                s["executed_queries"] = sum(r.get("sparql", {}).get("execution") == "ok" for r in rows)
            summary[category] = s
    report["summary"] = summary
    save(args.output, report)
    print(json.dumps({"output": str(args.output), "summary": summary,
                      "not_evaluated": len(report["not_evaluated"])}, indent=2))

if __name__ == "__main__":
    main()
