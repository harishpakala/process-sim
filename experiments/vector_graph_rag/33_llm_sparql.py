"""Experiment 33: exploratory ontology-grounded Llama 3.1 SPARQL generation.

Uses existing Experiment 31 vector rankings, not gold annotations, to prompt
local Ollama. Validates read-only SELECT queries and ontology predicates before
sending to GraphDB. Does not assert answer correctness from nonempty results.

From repo root:
 python experiments/vector_graph_rag/33_llm_sparql.py
 python experiments/vector_graph_rag/33_llm_sparql.py --no-execute
"""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("exp32", HERE / "32_execute_simple_sparql.py")
exp32 = module_from_spec(spec)
spec.loader.exec_module(exp32)

def ollama(url, model, prompt, timeout):
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)["response"]

def clean(text):
    match = re.search(r"```(?:sparql)?\s*(.*?)```", text, re.I | re.S)
    return (match.group(1) if match else text).strip()

def validate(query, allowed, candidates):
    # Fail closed: only a single basic SELECT query with candidate predicates.
    # No arbitrary SERVICE, GRAPH, property paths, or update operations.
    q = re.sub(r"#[^\n]*", "", query)
    if ";" in q or re.search(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD|WITH|USING|SERVICE|GRAPH|FROM|CONSTRUCT|DESCRIBE|ASK|BIND|VALUES|OPTIONAL|UNION|MINUS|EXISTS|FILTER|ORDER|GROUP|HAVING|OFFSET)\b", q, re.I):
        raise ValueError("Unsupported or unsafe SPARQL construct")
    prefixes = dict(re.findall(r"PREFIX\s+(\w+):\s*<([^>]+)>", q, re.I))
    q = re.sub(r"PREFIX\s+\w+:\s*<[^>]+>", "", q, flags=re.I).strip()
    if not re.match(r"^SELECT\s+(?:DISTINCT\s+)?(?:\?\w+\s+){1,4}WHERE\s*\{", q, re.I):
        raise ValueError("Expected simple SELECT ... WHERE query")
    if not re.search(r"\}\s*(?:LIMIT\s+\d+)?\s*$", q, re.I):
        raise ValueError("Invalid query ending")
    body = re.search(r"\{(.*?)\}", q, re.S).group(1).strip()
    triple = re.fullmatch(r"(\?\w+)\s+(<[^>]+>|\w+:\w+)\s+(\?\w+)\s*\.", body)
    if not triple:
        raise ValueError("Only one subject-predicate-object variable triple allowed")
    predicate = triple.group(2)
    if predicate.startswith("<"):
        uri = predicate[1:-1]
    else:
        prefix, local = predicate.split(":", 1)
        uri = prefixes.get(prefix, "") + local
    if uri not in allowed or uri not in candidates:
        raise ValueError("Predicate is not among retrieved ontology candidates")
    limit = re.search(r"\bLIMIT\s+(\d+)\s*$", q, re.I)
    if limit and int(limit.group(1)) > 100:
        raise ValueError("LIMIT exceeds 100")
    # Reconstruct query from validated URI to eliminate untrusted syntax.
    return uri, exp32.query_for(uri, 100)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--retrieval-results", type=Path, default=HERE / "data/simple_retrieval_31_results.json")
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--output", type=Path, default=HERE / "data/simple_llm_sparql_33_results.json")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--no-execute", action="store_true")
    a = ap.parse_args()
    if not 1 <= a.top_k <= 10 or a.timeout <= 0:
        ap.error("top-k must be 1..10 and timeout positive")
    retrieval = exp32.load(a.retrieval_results)
    index = exp32.load(a.index)
    if retrieval["index_sha256"] != hashlib.sha256(a.index.read_bytes()).hexdigest():
        ap.error("Ontology index mismatch")
    allowed = {c["uri"]: c["domain"] for c in index["concepts"]
               if c.get("kind") == "property" and c.get("uri")}
    rows = []
    for case in retrieval["results"]:
        candidates = case["methods"]["vector"]["top10_uris"][:a.top_k]
        if any(u not in allowed for u in candidates):
            raise ValueError("Unknown candidate URI")
        prompt = ("Generate exactly one read-only SPARQL SELECT query for this question. "
                  "Use ONLY one predicate from the listed candidate URIs. "
                  "Use a single triple pattern ?subject <URI> ?value . "
                  "No joins, FILTER, SERVICE, GRAPH, OPTIONAL, or other clauses. "
                  "Output only SPARQL. Never invent a predicate.\n"
                  f"Question: {case['question']}\n"
                  "Candidate predicates, ranked:\n" +
                  "\n".join(f"{i}. {uri}" for i, uri in enumerate(candidates, 1)) +
                  "\nReturn SELECT DISTINCT ?subject ?value WHERE { ?subject <URI> ?value . } LIMIT 100")
        row = {"id": case["id"], "question": case["question"],
               "gold_uri": case["gold_uri"], "candidates": candidates}
        start = time.monotonic()
        try:
            raw = ollama(a.ollama_url, a.model, prompt, a.timeout)
            row["raw_response"] = raw
            uri, query = validate(clean(raw), allowed, set(candidates))
            row.update({"predicate": uri, "query": query,
                        "predicate_correct": uri == case["gold_uri"],
                        "domain_correct": allowed[uri] == case["expected_domain"],
                        "validation": "ok"})
            if not a.no_execute:
                bindings = exp32.execute(a.endpoint, query, a.timeout)
                row.update({"execution": "ok", "rows": len(bindings),
                            "nonempty": bool(bindings), "sample_bindings": bindings[:3]})
        except Exception as e:
            row["error"] = str(e)[:500]
            row["validation"] = row.get("validation", "failed")
            if row["validation"] == "ok":
                row["execution"] = "failed"
        row["seconds"] = round(time.monotonic() - start, 2)
        rows.append(row)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps({
            "experiment": "33_exploratory_llm_sparql", "model": a.model,
            "endpoint": a.endpoint, "top_k": a.top_k,
            "limitations": ["Single-predicate SELECT only; not general natural-language-to-SPARQL.",
                            "Gold labels only used after generation for scoring.",
                            "Nonempty graph results do not prove answer correctness."],
            "results": rows}, indent=2) + "\n", encoding="utf-8")
        print(f"{case['id']}: valid={row['validation']=='ok'} "
              f"predicate_correct={row.get('predicate_correct')} "
              f"rows={row.get('rows','n/a')} time={row['seconds']}s", flush=True)
    n = len(rows)
    print(f"\nSummary: validated={sum(r['validation']=='ok' for r in rows)}/{n}; "
          f"correct predicate={sum(r.get('predicate_correct',False) for r in rows)}/{n}; "
          f"executed={sum(r.get('execution')=='ok' for r in rows)}/{n}")
    print("Saved:", a.output)

if __name__ == "__main__":
    main()
