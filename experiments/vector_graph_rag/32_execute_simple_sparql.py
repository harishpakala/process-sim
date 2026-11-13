"""Experiment 32: deterministic read-only SPARQL over GraphDB AAS.

Consumes the *actual* Experiment 31 retrieval output. Generates a one-triple
SELECT from the top-ranked vector or hybrid concept; optionally tests rank 2
as a diagnostic, never using gold annotations to choose the predicate.
No LLM, no SPARQL UPDATE, and no changes to GraphDB.

Run from repository root:
 python experiments/vector_graph_rag/32_execute_simple_sparql.py
 python experiments/vector_graph_rag/32_execute_simple_sparql.py --dry-run
 python experiments/vector_graph_rag/32_execute_simple_sparql.py --top-n 2
"""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "data/simple_retrieval_31_results.json"
DEFAULT_OUTPUT = HERE / "data/simple_sparql_32_results.json"


def load(path):
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def query_for(uri, limit):
    # Only use exact ontology-index URIs, validated in main().
    if not (uri.startswith(("http://", "https://")) and not any(ch.isspace() or ch in '<>"{}|^`\\' for ch in uri)):
        raise ValueError("Invalid SPARQL IRI")
    return ("SELECT DISTINCT ?subject ?value WHERE {\n"
            f"  ?subject <{uri}> ?value .\n"
            f"}}\nLIMIT {limit}")


def execute(endpoint, sparql, timeout):
    data = urllib.parse.urlencode({"query": sparql}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data, method="POST",
        headers={"Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.load(response)
    if "results" not in payload or "bindings" not in payload["results"]:
        raise ValueError("Endpoint did not return SPARQL SELECT JSON bindings")
    return payload["results"]["bindings"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--retrieval-results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--method", choices=["vector", "hybrid", "lexical"], default="vector")
    ap.add_argument("--top-n", type=int, choices=[1, 2], default=1,
                    help="Use 2 to inspect both top candidates; no gold-based reranking")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.limit < 1 or a.limit > 1000 or a.timeout < 1:
        ap.error("limit must be 1..1000 and timeout must be positive")
    if not a.endpoint.startswith(("http://", "https://")):
        ap.error("Endpoint must be HTTP(S)")
    results = load(a.retrieval_results)
    index = load(a.index)
    allowed = {c["uri"]: c["domain"] for c in index["concepts"]
               if c.get("kind") == "property" and c.get("uri")}
    if results.get("index_sha256") != hashlib.sha256(a.index.read_bytes()).hexdigest():
        ap.error("Retrieval results were generated with a different ontology index")
    rows = []
    for case in results["results"]:
        ranking = case["methods"][a.method]["top10_uris"]
        if len(ranking) < a.top_n:
            raise ValueError(f"Missing ranked candidates: {case['id']}")
        for rank, uri in enumerate(ranking[:a.top_n], 1):
            if uri not in allowed:
                raise ValueError(f"Unrecognized ontology property: {uri}")
            sparql = query_for(uri, a.limit)
            row = {"id": case["id"], "question": case["question"],
                   "method": a.method, "rank": rank, "predicate": uri,
                   "predicted_domain": allowed[uri], "query": sparql,
                   "expected_predicate": case["gold_uri"],
                   "expected_domain": case["expected_domain"],
                   "predicate_correct": uri == case["gold_uri"],
                   "domain_correct": allowed[uri] == case["expected_domain"]}
            if a.dry_run:
                row["status"] = "not_executed"
                print(f"\n{case['id']} rank {rank}: {uri}\n{sparql}")
            else:
                try:
                    bindings = execute(a.endpoint, sparql, a.timeout)
                    row["status"] = "ok"
                    row["returned_rows"] = len(bindings)
                    row["nonempty"] = bool(bindings)
                    row["sample_bindings"] = bindings[:3]
                    print(f"{case['id']} rank={rank} domain={allowed[uri]} "
                          f"predicate_correct={row['predicate_correct']} "
                          f"rows={len(bindings)} (max {a.limit})", flush=True)
                except (urllib.error.URLError, ValueError, json.JSONDecodeError,
                        TimeoutError) as e:
                    row["status"] = "error"
                    row["error"] = str(e)[:500]
                    print(f"{case['id']} rank={rank} ERROR: {row['error']}", flush=True)
            rows.append(row)
            save(a, results, rows)
    print("\nSummary:")
    for rank in range(1, a.top_n + 1):
        subset = [r for r in rows if r["rank"] == rank]
        n = len(subset)
        print(f"rank {rank}: correct predicates={sum(r['predicate_correct'] for r in subset)}/{n}; "
              f"correct domains={sum(r['domain_correct'] for r in subset)}/{n}")
        if not a.dry_run:
            print(f"        executed={sum(r['status']=='ok' for r in subset)}/{n}; "
                  f"nonempty={sum(r.get('nonempty',False) for r in subset)}/{n}")
    print("Saved:", a.output)


def save(a, retrieval, rows):
    report = {
        "experiment": "32_deterministic_sparql_graphdb",
        "endpoint": a.endpoint, "method": a.method, "top_n": a.top_n,
        "limit_per_query": a.limit,
        "retrieval_results_sha256": hashlib.sha256(a.retrieval_results.read_bytes()).hexdigest(),
        "retrieval_index_sha256": retrieval["index_sha256"],
        "results": rows,
        "limitations": [
            "One-predicate SELECT template only, not question-specific query planning.",
            "No asset-specific filtering, graph joins, or cross-domain traversal.",
            "GraphDB row counts are capped by LIMIT; nonempty is not answer correctness.",
            "Gold predicates used for post-hoc evaluation only, never for query generation.",
            "Top-2 mode is diagnostic; it does not automatically choose the correct candidate.",
            "Curated ten-question benchmark, not an independent held-out evaluation.",
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
