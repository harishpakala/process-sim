"""Experiment 28B: local Ollama concept selection on six reviewed DTWiSE questions.

No external API key or pip packages needed. Frozen candidate sets are used;
only candidate IDs are returned by the LLM. Gold is never sent to Ollama.
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).parent


def module(name, filename):
    spec = spec_from_file_location(name, ROOT / filename)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ollama_select(url, model, question, candidates, index, timeout):
    options = []
    for c in candidates:
        info = index[c["uri"]]
        options.append({
            "id": c["id"],
            "name": c["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1],
            "kind": info.get("kind"),
            "label": info.get("label"),
            "description": info.get("description"),
        })
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"selected_candidate_ids": {
            "type": "array", "items": {"type": "integer"}}},
        "required": ["selected_candidate_ids"],
    }
    messages = [
        {"role": "system", "content":
         "You select minimal, necessary ontology concepts to answer engineering questions. "
         "Choose only IDs from the provided candidates. Do not infer engineering domains "
         "from concept names or namespaces. Asset identifiers can be relevant for joining "
         "records, but they do not independently identify answer-bearing domains. "
         "Return only the requested JSON."},
        {"role": "user", "content": json.dumps({
            "question": question, "candidates": options,
            "instruction": "Select the smallest sufficient set of concepts. "
                           "Exclude merely related or redundant concepts. "
                           "Return an empty list if none is needed."
        }, ensure_ascii=False)}
    ]
    body = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "format": schema, "options": {"temperature": 0, "num_ctx": 4096}
    }).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    elapsed = time.perf_counter() - start
    raw = payload.get("message", {}).get("content", "")
    if not raw:
        raise ValueError("Ollama returned empty content")
    result = json.loads(raw)
    ids = result["selected_candidate_ids"]
    allowed = {c["id"] for c in candidates}
    if not isinstance(ids, list) or any(type(i) is not int or i not in allowed for i in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"Invalid candidate selection: {ids!r}")
    return ids, elapsed, {
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    p.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    p.add_argument("--reviewed", type=Path, default=ROOT / "data/reviewed_concepts_6.json")
    p.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    p.add_argument("--output", type=Path, default=ROOT / "data/ollama_concept_selection_28.json")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--mode", choices=("lexical", "vector", "hybrid"), default="hybrid")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    if a.top_k < 1 or a.limit < 0 or a.timeout < 1:
        p.error("top-k and timeout must be positive; limit must be nonnegative")
    common = module("experiment28", "28_evaluate_llm_concept_selection.py")
    policy = module("concept_role_policy", "concept_role_policy.py")
    exp25 = module("exp25", "25_evaluate_ontology_resolved_domains.py")
    idx, benchmark, reviewed, retrieval = [read(x) for x in (a.index, a.benchmark, a.reviewed, a.retrieval)]
    index = {c["uri"]: c for c in idx["concepts"] if c.get("uri")}
    mapping = exp25.resolver(idx)
    questions = {c["id"]: c for c in benchmark["cases"]}
    retrieved = {r["id"]: r for r in retrieval["results"]}
    if len(questions) != len(benchmark["cases"]) or len(retrieved) != len(retrieval["results"]):
        raise ValueError("Duplicate benchmark or retrieval IDs")
    cases = reviewed["cases"][:a.limit or None]
    if any(c["id"] not in questions or c["id"] not in retrieved for c in cases):
        raise ValueError("Reviewed ID absent from benchmark/retrieval")
    rows = []
    for case in cases:
        qid = case["id"]
        candidates = common.candidate_set(retrieved[qid][a.mode]["hits"], a.top_k, index)
        gold = [x["uri"] for x in case["required"]]
        if any(uri not in index for uri in gold):
            raise ValueError(f"Reviewed URI not indexed: {qid}")
        baseline = common.concept_metrics(gold, [c["uri"] for c in candidates])
        row = {"id": qid, "question": questions[qid]["question"],
               "candidate_uris": [c["uri"] for c in candidates],
               "topk_baseline": baseline}
        if a.dry_run:
            print(f"{qid}: candidates={len(candidates)}, gold-in-candidates={baseline['matched']}/{len(gold)}")
        else:
            try:
                ids, elapsed, usage = ollama_select(a.ollama_url, a.model,
                    questions[qid]["question"], candidates, index, a.timeout)
            except (urllib.error.URLError, TimeoutError) as exc:
                raise RuntimeError(f"Ollama connection failed: {exc}. Check 'ollama list' and server.") from exc
            selected = [c["uri"] for c in candidates if c["id"] in ids]
            evidence = [uri for uri in selected if policy.eligible_for_domain_evidence(uri)]
            linking = [uri for uri in selected if not policy.eligible_for_domain_evidence(uri)]
            domains = sorted({next(iter(mapping[uri])) for uri in evidence if len(mapping.get(uri, ())) == 1})
            cm = common.concept_metrics(gold, selected)
            row["ollama"] = {
                "selected_uris": selected, "domain_evidence_uris": evidence,
                "graph_linking_uris": linking, "predicted_domains": domains,
                "concept_metrics": cm,
                "domain_metrics": exp25.metrics(questions[qid]["expected_domains"], domains),
                "latency_seconds": round(elapsed, 3), "usage": usage,
            }
            print(f"{qid}: precision={cm['precision']:.3f} recall={cm['recall']:.3f} "
                  f"complete={cm['complete_coverage']} domains={domains} time={elapsed:.1f}s")
        rows.append(row)
        report = {
            "experiment": "28b_ollama_concept_selection",
            "model": a.model, "dry_run": a.dry_run,
            "mode": a.mode, "top_k": a.top_k, "completed": len(rows),
            "results": rows,
            "input_sha256": {n: hashlib.sha256(f.read_bytes()).hexdigest() for n, f in (
                ("index", a.index), ("benchmark", a.benchmark),
                ("reviewed", a.reviewed), ("retrieval", a.retrieval))},
            "limitations": [
                "Only six reviewed cases, no untouched holdout.",
                "Gold annotations are never supplied to Ollama.",
                "Frozen hybrid retrieval may use weight 0.70; not a rerun at 0.75.",
                "Predicted domains use unique URI associations, not rank voting.",
                "Graph traversal is not executed.",
            ],
        }
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if rows and not a.dry_run:
        for label, scores in (
            ("top-k baseline", [r["topk_baseline"] for r in rows]),
            ("Ollama", [r["ollama"]["concept_metrics"] for r in rows])):
            print(f"{label}: precision={sum(s['precision'] for s in scores)/len(scores):.3f}, "
                  f"recall={sum(s['recall'] for s in scores)/len(scores):.3f}, "
                  f"complete={sum(s['complete_coverage'] for s in scores)}/{len(scores)}")
    print("Wrote:", a.output)


if __name__ == "__main__":
    main()
