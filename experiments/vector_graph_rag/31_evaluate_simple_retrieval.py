"""Experiment 31: retrieval-only DTWiSE feasibility benchmark (no generative LLM).

Evaluates lexical TF-IDF, nomic-embed-text vector cosine similarity and
weighted reciprocal-rank fusion (RRF, k=60) over ontology properties.
This is a curated, easy, non-held-out benchmark, not the historical frozen
retrieval pipeline. Do not compare its scores as if retrieval were identical.
Requires a running Ollama instance with nomic-embed-text installed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--benchmark", type=Path, default=HERE / "data/simple_questions_10.json")
    parser.add_argument("--output", type=Path, default=HERE / "data/simple_retrieval_31_results.json")
    parser.add_argument("--embedding-model", default="nomic-embed-text:latest")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--vector-weight", type=float, default=0.75)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.vector_weight <= 1 or args.timeout <= 0:
        parser.error("vector-weight must be in [0,1] and timeout positive")

    # Reuse only the retrieval primitives of Experiment 30.
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("exp30", HERE / "30_evaluate_simple_questions.py")
    exp30 = module_from_spec(spec)
    spec.loader.exec_module(exp30)

    index_data = exp30.read(args.index)
    benchmark = exp30.read(args.benchmark)
    concepts = sorted((c for c in index_data["concepts"]
                       if c.get("kind") == "property" and c.get("uri")),
                      key=lambda c: c["uri"])
    uris = [c["uri"] for c in concepts]
    if len(uris) != len(set(uris)):
        raise ValueError("Duplicate property URIs")
    uri_to_index = {u: i for i, u in enumerate(uris)}
    cases = benchmark["cases"]
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate question IDs")
    for c in cases:
        if len(c["required"]) != 1 or len(c["expected_domains"]) != 1:
            raise ValueError("Only single-concept, single-domain questions supported")
        gold = c["required"][0]
        if gold["uri"] not in uri_to_index:
            raise ValueError(f"Gold URI not indexed: {c['id']}")
        indexed = concepts[uri_to_index[gold["uri"]]]
        if indexed["domain"] != gold["domain"] or indexed["domain"] != c["expected_domains"][0]:
            raise ValueError(f"Domain annotation mismatch: {c['id']}")
    print(f"Questions: {len(cases)}; ontology properties: {len(concepts)}")
    if args.dry_run:
        for c in cases:
            print(f"{c['id']}: {c['question']} -> {c['required'][0]['uri']}")
        return

    index_sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    cache = args.output.with_name("simple_questions_10_embedding_cache.json")
    cached = exp30.read(cache) if cache.exists() else {}
    if (cached.get("index_sha256") == index_sha
        and cached.get("model") == args.embedding_model
        and cached.get("uris") == uris):
        vectors = cached["vectors"]
        print("Reusing ontology embedding cache")
    else:
        print(f"Embedding {len(concepts)} ontology properties with {args.embedding_model}...", flush=True)
        vectors = exp30.embed(args.ollama_url, args.embedding_model,
                              [exp30.concept_text(c) for c in concepts], args.timeout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({
            "index_sha256": index_sha, "model": args.embedding_model,
            "uris": uris, "vectors": vectors,
        }), encoding="utf-8")
    rows = []
    for c in cases:
        question = c["question"]
        gold_uri = c["required"][0]["uri"]
        gold_index = uri_to_index[gold_uri]
        lexical = exp30.lexical_ranking(question, concepts)
        qvec = exp30.embed(args.ollama_url, args.embedding_model, [question], args.timeout)[0]
        vector = exp30.vector_ranking(qvec, vectors, concepts)
        hybrid = exp30.fusion(lexical, vector, concepts, args.vector_weight)
        methods = {}
        for name, order in (("lexical", lexical), ("vector", vector), ("hybrid", hybrid)):
            rank = order.index(gold_index) + 1
            top_uri = concepts[order[0]]["uri"]
            top_domain = concepts[order[0]]["domain"]
            methods[name] = {
                "gold_rank": rank,
                "recall_at_1": rank <= 1,
                "recall_at_5": rank <= 5,
                "recall_at_10": rank <= 10,
                "top1_uri": top_uri,
                "top1_domain": top_domain,
                "top1_domain_correct": top_domain == c["expected_domains"][0],
                "top10_uris": [concepts[i]["uri"] for i in order[:10]],
            }
        rows.append({
            "id": c["id"], "question": question,
            "gold_uri": gold_uri, "expected_domain": c["expected_domains"][0],
            "methods": methods,
        })
        print(f"{c['id']}: gold rank L/V/H="
              f"{methods['lexical']['gold_rank']}/"
              f"{methods['vector']['gold_rank']}/"
              f"{methods['hybrid']['gold_rank']}", flush=True)
        save(args, rows, index_sha)

    print("\nSummary (counts out of 10):")
    for name in ("lexical", "vector", "hybrid"):
        m = [r["methods"][name] for r in rows]
        print(f"{name:7} R@1={sum(x['recall_at_1'] for x in m)}/{len(m)} "
              f"R@5={sum(x['recall_at_5'] for x in m)}/{len(m)} "
              f"R@10={sum(x['recall_at_10'] for x in m)}/{len(m)} "
              f"domain@1={sum(x['top1_domain_correct'] for x in m)}/{len(m)}")
    print("Saved:", args.output)


def save(args, rows, index_sha):
    summary = {}
    for name in ("lexical", "vector", "hybrid"):
        values = [r["methods"][name] for r in rows]
        summary[name] = {
            "evaluated": len(values),
            "recall_at_1": sum(v["recall_at_1"] for v in values),
            "recall_at_5": sum(v["recall_at_5"] for v in values),
            "recall_at_10": sum(v["recall_at_10"] for v in values),
            "top1_domain_correct": sum(v["top1_domain_correct"] for v in values),
        }
    report = {
        "experiment": "31_simple_retrieval_only",
        "methods": ["lexical", "vector", "hybrid"],
        "embedding_model": args.embedding_model,
        "vector_weight": args.vector_weight,
        "rrf_k": 60,
        "candidate_universe": "ontology properties only",
        "index_sha256": index_sha,
        "benchmark_sha256": hashlib.sha256(args.benchmark.read_bytes()).hexdigest(),
        "summary": summary,
        "results": rows,
        "limitations": [
            "Ten easy, curated single-domain questions, authored after earlier experiments.",
            "Not an untouched holdout; expected ontology concepts were verified before execution.",
            "Property-only TF-IDF + Ollama embeddings + RRF is a separate implementation from the earlier frozen retrieval experiment.",
            "No generative LLM selection, graph traversal, or instance-level question answering.",
            "Top-1 domain accuracy is based on the domain of the top-ranked ontology concept.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
