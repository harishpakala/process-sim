"""Run the frozen 15-question benchmark through existing hybrid schema retrieval.

Uses 06_evaluate_hybrid_retrieval.py rankings unchanged. Domain predictions are
derived from retrieved hits, never from benchmark labels or domain counts.
"""
import argparse
import importlib.util
import json
import urllib.request
from pathlib import Path

ROOT = Path("experiments/vector_graph_rag")
DEFAULT_BENCHMARK = ROOT / "data/benchmark_15.json"
DEFAULT_RECORDS = ROOT / "data/schema_records.jsonl"
DEFAULT_VECTORS = ROOT / "data/schema_vectors.jsonl"
DEFAULT_OUTPUT = ROOT / "data/retrieval_results_15.json"

def load_engine():
    spec = importlib.util.spec_from_file_location(
        "dtwise_hybrid_retrieval", Path(__file__).with_name("06_evaluate_hybrid_retrieval.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def select_domains(hits, max_domains=3, relative_threshold=0.65):
    """Independent heuristic; aggregate discounted evidence in top-k concept hits."""
    scores = {}
    for rank, hit in enumerate(hits, 1):
        domain = hit.get("domain")
        if domain:
            scores[domain] = scores.get(domain, 0.0) + 1.0 / (rank + 5)
    if not scores:
        return []
    ordered = sorted(scores, key=lambda d: (-scores[d], d))
    top = scores[ordered[0]]
    return [d for d in ordered if scores[d] >= relative_threshold * top][:max_domains]

def temporal_intent(question):
    """Transparent lexical baseline; not part of domain retrieval."""
    q = question.lower()
    return any(s in q for s in ("observations", "recorded between", "historical", "time series"))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    ap.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    ap.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--top-k", type=int, default=30)
    ap.add_argument("--vector-weight", type=float, default=0.7)
    ap.add_argument("--domain-threshold", type=float, default=0.65)
    ap.add_argument("--max-domains", type=int, default=3)
    args = ap.parse_args()
    if args.top_k < 10 or not 0 <= args.vector_weight <= 1 or not 0 < args.domain_threshold <= 1 or args.max_domains < 1:
        ap.error("Require top-k >= 10, vector-weight in [0,1], threshold in (0,1], max-domains >= 1")
    engine = load_engine()
    records = engine.load_jsonl(args.records)
    vectors = {v["id"]: v for v in engine.load_jsonl(args.vectors)}
    if len(vectors) != len(records) or any(r["id"] not in vectors for r in records):
        raise ValueError("Schema vectors do not match schema records")
    models = {v["model"] for v in vectors.values()}
    if len(models) != 1:
        raise ValueError("Expected one embedding model")
    model = models.pop()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8-sig"))
    results = []
    for case in benchmark["cases"]:
        question = case["question"]
        req = urllib.request.Request(
            args.endpoint.rstrip("/") + "/api/embed",
            json.dumps({"model": model, "input": question}).encode("utf-8"),
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as response:
            qv = json.load(response)["embeddings"][0]
        ranked, _ = engine.ranks(records, vectors, question, qv, args.top_k, args.vector_weight)
        result = {"id": case["id"], "question": question, "predicted_historical": temporal_intent(question)}
        for mode, hits in ranked.items():
            concise = [{"domain": h["domain"], "uri": h["uri"], "kind": h["kind"], "id": h["id"]} for h in hits]
            result[mode] = {
                "hits": concise,
                "selected_domains": select_domains(concise, args.max_domains, args.domain_threshold),
            }
        results.append(result)
        print(f'{case["id"]}: hybrid domains={result["hybrid"]["selected_domains"]}')
    output = {"version": "dtwise-retrieval-15-v1", "embedding_model": model,
              "parameters": {"top_k": args.top_k, "vector_weight": args.vector_weight,
                             "domain_threshold": args.domain_threshold, "max_domains": args.max_domains},
              "notes": ["Domain selection is a heuristic, not trained or calibrated on gold labels.",
                        "Lexical scoring in script 06 is token overlap, not BM25.",
                        "Temporal prediction is a separate lexical baseline."],
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Wrote:", args.output)

if __name__ == "__main__":
    main()
