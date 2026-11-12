"""Exploratory fusion-weight ablation on six reviewed concept questions.

Reuses the unchanged ranking engine from script 06. No gold labels are used
to rank or tune results. All weights are reported; no best weight is selected.
Requires the original schema records/vectors and local Ollama embedding model.
"""
import argparse
import hashlib
import importlib.util
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DEFAULT_WEIGHTS = (0.0, 0.25, 0.5, 0.7, 0.75, 0.9, 1.0)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def embed(question, model, endpoint):
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/embed",
        json.dumps({"model": model, "input": question}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    return result["embeddings"][0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotations", type=Path, default=ROOT / "data/reviewed_concepts_6.json")
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--records", type=Path, default=ROOT / "data/schema_records.jsonl")
    ap.add_argument("--vectors", type=Path, default=ROOT / "data/schema_vectors.jsonl")
    ap.add_argument("--baseline", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/concept_fusion_ablation_6.json")
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--weights", type=float, nargs="+", default=DEFAULT_WEIGHTS)
    ap.add_argument("--top-k", type=int, default=30)
    args = ap.parse_args()
    if args.top_k < 10 or not args.weights or any(not 0 <= w <= 1 for w in args.weights):
        ap.error("Require top-k >= 10 and weights in [0, 1]")
    if len(set(args.weights)) != len(args.weights):
        ap.error("Weights must be unique")
    engine = load_module(ROOT / "06_evaluate_hybrid_retrieval.py", "dtwise_engine")
    evaluator = load_module(ROOT / "20_evaluate_reviewed_concepts.py", "dtwise_concept_eval")
    load = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
    annotations, benchmark, index = load(args.annotations), load(args.benchmark), load(args.index)
    if annotations.get("status") != "user_reviewed":
        raise ValueError("Only user-reviewed annotations are allowed")
    questions = {c["id"]: c["question"] for c in benchmark["cases"]}
    ids = [c["id"] for c in annotations["cases"]]
    if len(ids) != len(set(ids)) or any(i not in questions for i in ids):
        raise ValueError("Annotation IDs must be unique and present in benchmark")
    records = engine.load_jsonl(args.records)
    vectors_list = engine.load_jsonl(args.vectors)
    vectors = {v["id"]: v for v in vectors_list}
    if len(vectors) != len(vectors_list) or len(vectors) != len(records) or any(r["id"] not in vectors for r in records):
        raise ValueError("Records/vectors mismatch; rebuild using original records")
    models = {v["model"] for v in vectors.values()}
    if len(models) != 1:
        raise ValueError("Expected a single embedding model")
    model = models.pop()
    queries = {i: embed(questions[i], model, args.endpoint) for i in ids}
    by_weight = {}
    baseline_comparison = None
    for weight in args.weights:
        results = []
        for i in ids:
            ranked, _ = engine.ranks(records, vectors, questions[i], queries[i], args.top_k, weight)
            results.append({"id": i, **{
                mode: {"hits": [{"domain": r["domain"], "uri": r["uri"],
                                  "kind": r["kind"], "id": r["id"]} for r in hits]}
                for mode, hits in ranked.items()
            }})
        evaluation = evaluator.evaluate(annotations, {"results": results}, index)
        by_weight[f"{weight:g}"] = {
            "vector_weight": weight, "lexical_weight": 1 - weight,
            "hybrid": evaluation["results"]["hybrid"],
        }
    if args.baseline.exists() and 0.7 in args.weights:
        original = load(args.baseline)
        if original.get("parameters", {}).get("vector_weight") != 0.7:
            raise ValueError("Baseline is not the original 0.7 vector-weight configuration")
        if original.get("parameters", {}).get("top_k", 0) < 10:
            raise ValueError("Baseline top_k must be >= 10")
        baseline_eval = evaluator.evaluate(annotations, original, index)
        old_cases = {r["id"]: r for r in original["results"]}
        # Validate the baseline's hybrid ranked identities against a fresh
        # 0.7 ranking rather than merely comparing rounded aggregate scores.
        mismatches = []
        for i in ids:
            fresh, _ = engine.ranks(records, vectors, questions[i], queries[i], args.top_k, 0.7)
            fresh_keys = [(r["domain"], r["uri"]) for r in fresh["hybrid"][:10]]
            old_keys = [(r.get("domain"), r.get("uri")) for r in old_cases[i]["hybrid"]["hits"][:10]]
            if fresh_keys != old_keys:
                mismatches.append(i)
        baseline_comparison = {
            "original_baseline_hybrid_summary": baseline_eval["results"]["hybrid"]["summary"],
            "baseline_top10_identical_to_recomputed": not mismatches,
            "mismatched_question_ids": mismatches,
            "warning": ("Baseline differs: check records, vectors, or embedding model before interpreting ablation"
                        if mismatches else None),
        }
    output = {
        "experiment": "exploratory_reviewed_concept_fusion_weight_ablation",
        "interpretation": "In-sample development-set sensitivity analysis only; no selected optimum or held-out performance claim.",
        "ranking_engine": "06_evaluate_hybrid_retrieval.py ranks() unchanged; RRF constant 60",
        "weights": list(args.weights), "top_k": args.top_k,
        "embedding_model": model, "reviewed_question_ids": ids,
        "sha256": {k: digest(p) for k, p in {
            "annotations": args.annotations, "benchmark": args.benchmark,
            "index": args.index, "records": args.records, "vectors": args.vectors
        }.items()},
        "baseline_comparison": baseline_comparison,
        "results_by_weight": by_weight,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("Exploratory in-sample comparison; no optimal weight is claimed.")
    print("weight  Recall@5  Recall@10  Complete@10  MRR")
    for key, entry in by_weight.items():
        s = entry["hybrid"]["summary"]
        print(f"{key:>6}  {s['mean_required_recall_at_5']:>8.3f}  "
              f"{s['mean_required_recall_at_10']:>9.3f}  "
              f"{s['complete_required_coverage_at_10']:>11.3f}  "
              f"{s['mean_reciprocal_rank']:>5.3f}")
    if baseline_comparison is not None:
        print("Original 0.7 baseline top-10 identical:",
              baseline_comparison["baseline_top10_identical_to_recomputed"])
        if baseline_comparison["mismatched_question_ids"]:
            print("Mismatches:", baseline_comparison["mismatched_question_ids"])
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
