"""Simple DTWiSE feasibility evaluation: 10 curated questions, Ollama-only.

Retrieves over ontology properties with TF-IDF lexical and nomic embeddings,
combines ranks with reciprocal rank fusion, then applies the frozen minimal
Llama 3.1 selector. This is a NEW retrieval configuration, not the historical
frozen hybrid baseline; its scores must be reported separately.
"""
import argparse
import hashlib
import json
import math
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = spec_from_file_location(name, HERE / filename)
    m = module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def post(url, endpoint, payload, timeout):
    request = urllib.request.Request(
        url.rstrip("/") + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def tokens(s):
    # Split camel case and punctuation, without domain namespace cues.
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return re.findall(r"[a-z]+|[0-9]+", s.lower())


def concept_text(c):
    local = c["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return " ".join([local] + c.get("labels", []) + c.get("descriptions", []))


def lexical_ranking(question, concepts):
    docs = [Counter(tokens(concept_text(c))) for c in concepts]
    df = Counter(t for d in docs for t in d)
    n = len(docs)
    query = Counter(tokens(question))
    def weights(tf):
        return {t: (1 + math.log(count)) * (math.log((n + 1) / (df[t] + 1)) + 1)
                for t, count in tf.items()}
    qw = weights(query)
    qnorm = math.sqrt(sum(v * v for v in qw.values())) or 1
    scores = []
    for d in docs:
        dw = weights(d)
        norm = math.sqrt(sum(v * v for v in dw.values())) or 1
        scores.append(sum(v * dw.get(t, 0) for t, v in qw.items()) / (qnorm * norm))
    return sorted(range(n), key=lambda i: (-scores[i], concepts[i]["uri"]))


def embed(url, model, texts, timeout):
    # One embedding request per text, compatible with Ollama /api/embeddings.
    vectors = []
    for t in texts:
        data = post(url, "/api/embeddings", {"model": model, "prompt": t}, timeout)
        vec = data.get("embedding")
        if not isinstance(vec, list) or not vec:
            raise ValueError("Ollama embedding response missing vector")
        vectors.append(vec)
    return vectors


def vector_ranking(q, vectors, concepts):
    qnorm = math.sqrt(sum(x*x for x in q)) or 1
    scores = []
    for v in vectors:
        if len(v) != len(q):
            raise ValueError("Embedding dimensions mismatch")
        norm = math.sqrt(sum(x*x for x in v)) or 1
        scores.append(sum(x*y for x,y in zip(q,v)) / (qnorm*norm))
    return sorted(range(len(vectors)), key=lambda i: (-scores[i], concepts[i]["uri"]))


def fusion(lexical, vector, concepts, weight):
    lr = {i:r for r,i in enumerate(lexical,1)}
    vr = {i:r for r,i in enumerate(vector,1)}
    return sorted(range(len(concepts)), key=lambda i: (
        -(1-weight)/(60+lr[i]) - weight/(60+vr[i]), concepts[i]["uri"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=HERE / "data/simple_questions_10.json")
    ap.add_argument("--output", type=Path, default=HERE / "data/simple_questions_10_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.top_k < 1 or a.limit < 0 or not 0 <= a.vector_weight <= 1:
        ap.error("Invalid top-k, limit or vector-weight")
    index_data, benchmark = read(a.index), read(a.benchmark)
    # Restrict to ontology properties; shapes/classes are outside this benchmark.
    concepts = sorted([c for c in index_data["concepts"]
                       if c.get("kind") == "property" and c.get("uri")],
                      key=lambda c: c["uri"])
    by_uri = {c["uri"]: c for c in concepts}
    if len(by_uri) != len(concepts):
        raise ValueError("Duplicate property URIs: cannot rank unambiguously")
    cases = benchmark["cases"][:a.limit or None]
    for case in cases:
        if len(case["required"]) != 1 or len(case["expected_domains"]) != 1:
            raise ValueError("Benchmark requires one concept and one domain per question")
        gold = case["required"][0]
        if gold["uri"] not in by_uri or by_uri[gold["uri"]]["domain"] != gold["domain"]:
            raise ValueError(f"Gold concept missing or wrong domain: {case['id']}")
    print(f"Ontology property candidates: {len(concepts)}; questions: {len(cases)}")
    if a.dry_run:
        for c in cases:
            print(c["id"], c["question"], "=>", c["required"][0]["uri"])
        return
    exp29 = module("exp29", "29_ablate_ollama_concept_prompts.py")
    exp25 = module("exp25", "25_evaluate_ontology_resolved_domains.py")
    exp28 = module("exp28", "28_evaluate_llm_concept_selection.py")
    policy = module("concept_role_policy", "concept_role_policy.py")
    mapping = exp25.resolver(index_data)
    # Cache embeddings by ontology SHA and model, never by evaluation gold.
    cache = a.output.with_name("simple_questions_10_embedding_cache.json")
    sha = hashlib.sha256(a.index.read_bytes()).hexdigest()
    cached = read(cache) if cache.exists() else {}
    if (cached.get("index_sha256") == sha and
        cached.get("model") == a.embedding_model and
        cached.get("uris") == [c["uri"] for c in concepts]):
        vectors = cached["vectors"]
        print("Using cached ontology embeddings")
    else:
        print("Embedding ontology properties with", a.embedding_model, flush=True)
        vectors = embed(a.ollama_url, a.embedding_model,
                        [concept_text(c) for c in concepts], a.timeout)
        cache.write_text(json.dumps({
            "index_sha256": sha, "model": a.embedding_model,
            "uris": [c["uri"] for c in concepts], "vectors": vectors,
        }), encoding="utf-8")
    rows = []
    for case in cases:
        q = case["question"]
        gold = case["required"][0]["uri"]
        lexical = lexical_ranking(q, concepts)
        qvec = embed(a.ollama_url, a.embedding_model, [q], a.timeout)[0]
        vector = vector_ranking(qvec, vectors, concepts)
        hybrid = fusion(lexical, vector, concepts, a.vector_weight)
        ranks = {name: next((rank for rank, i in enumerate(order, 1)
                             if concepts[i]["uri"] == gold), None)
                 for name, order in (("lexical", lexical), ("vector", vector),
                                     ("hybrid", hybrid))}
        chosen = hybrid[:a.top_k]
        candidates = [{"id": j, "uri": concepts[i]["uri"]}
                      for j,i in enumerate(chosen, 1)]
        selected, _, latency, calls = exp29.run_strategy(
            "minimal", q, candidates, by_uri, a)
        evidence = [u for u in selected if policy.eligible_for_domain_evidence(u)]
        linking = [u for u in selected if not policy.eligible_for_domain_evidence(u)]
        domains = sorted({next(iter(mapping[u])) for u in evidence
                          if len(mapping.get(u, ())) == 1})
        row = {
            "id": case["id"], "question": q,
            "gold_uri": gold, "expected_domains": case["expected_domains"],
            "gold_rank": ranks,
            "recall_at_10": {name: (rank is not None and rank <= 10)
                             for name, rank in ranks.items()},
            "candidate_uris": [c["uri"] for c in candidates],
            "selected_uris": selected,
            "domain_evidence_uris": evidence,
            "graph_linking_uris": linking,
            "predicted_domains": domains,
            "concept_metrics": exp28.concept_metrics([gold], selected),
            "domain_metrics": exp25.metrics(case["expected_domains"], domains),
            "latency_seconds": latency, "calls": calls,
        }
        rows.append(row)
        save(a, rows, sha, cache)
        print(f"{case['id']}: rank(L/V/H)={ranks['lexical']}/{ranks['vector']}/{ranks['hybrid']} "
              f"selected={gold in selected} domains={domains} "
              f"exact={row['domain_metrics']['exact']} time={latency:.1f}s", flush=True)
    n = len(rows)
    print("\nFinal results:")
    for method in ("lexical", "vector", "hybrid"):
        print(f"{method} Recall@10: {sum(r['recall_at_10'][method] for r in rows)}/{n}")
    print(f"LLM required-concept selected: {sum(r['gold_uri'] in r['selected_uris'] for r in rows)}/{n}")
    print(f"Domain exact match: {sum(r['domain_metrics']['exact'] for r in rows)}/{n}")
    print("Saved:", a.output)


def save(a, rows, index_sha, cache):
    report = {
        "experiment": "simple_10_curated_feasibility",
        "model": a.model, "embedding_model": a.embedding_model,
        "retrieval": "property-only TF-IDF cosine + nomic cosine + RRF(k=60)",
        "vector_weight": a.vector_weight, "top_k": a.top_k,
        "prompt": "experiment29 minimal", "seed": a.seed,
        "index_sha256": index_sha,
        "benchmark_sha256": hashlib.sha256(a.benchmark.read_bytes()).hexdigest(),
        "embedding_cache": str(cache),
        "results": rows,
        "limitations": [
            "Curated easy single-domain questions authored after earlier model evaluations; not held out.",
            "New retrieval implementation and property-only candidate universe; do not compare numerically with frozen historical retrieval.",
            "Exact domain match can fail due to additional selected concepts even when required concept is selected.",
            "Only concept grounding and domain resolution evaluated; no instance answers or graph traversal.",
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
