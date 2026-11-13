"""Experiment 29: controlled local Ollama prompt ablation on frozen DTWiSE candidates.

Strategies: minimal (28B-equivalent), recall, two_stage (requirements then IDs).
All strategies use the same candidate IDs, model, decoding and input order.
The second stage sees only the question, candidates and model-derived requirements.
Gold annotations are used for scoring only, never included in prompts.
"""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = spec_from_file_location(name, HERE / path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ask(url, model, messages, schema, timeout, seed, num_ctx):
    body = json.dumps({
        "model": model, "messages": messages, "stream": False,
        "format": schema,
        "options": {"temperature": 0, "seed": seed, "num_ctx": num_ctx},
    }).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    seconds = time.perf_counter() - start
    raw = payload.get("message", {}).get("content")
    if not raw:
        raise ValueError("Ollama returned empty message.content")
    parsed = json.loads(raw)
    return parsed, seconds, {
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
    }


IDS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"selected_candidate_ids": {
        "type": "array", "items": {"type": "integer"}}},
    "required": ["selected_candidate_ids"],
}
REQUIREMENTS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"information_requirements": {
        "type": "array", "items": {"type": "string"}}},
    "required": ["information_requirements"],
}
SYSTEM = (
    "You select ontology concepts needed to answer engineering questions. "
    "Only select IDs of provided candidate concepts. "
    "Do not infer engineering domains from concept namespaces. "
    "Asset identifiers may link records but do not independently establish "
    "which engineering domain contains the answer. Return only schema-valid JSON."
)
MINIMAL = (
    "Select the smallest sufficient set of concepts. "
    "Exclude merely related or redundant concepts. "
    "Return an empty list if none is needed."
)
RECALL = (
    "Identify every distinct information requirement in the question and "
    "select all provided concepts necessary to satisfy ANY of those requirements. "
    "For questions requiring multiple properties or relationships, preserve each "
    "required concept, even when several come from one domain. "
    "Do not omit a necessary concept merely to minimize the list. "
    "Exclude concepts that are unrelated to answering the question. "
    "Identifiers used only for graph linking are optional, not domain evidence. "
    "Return an empty list only if no candidates are relevant."
)
STAGE1 = (
    "Break the question into all distinct information requirements, including "
    "each requested property, relationship, entity and cross-system linkage. "
    "Do not select ontology candidates or infer domain labels. "
    "Use short phrases grounded only in the question."
)
STAGE2 = (
    "Use the information requirements below as a checklist. "
    "Select all candidate concepts needed to cover the requirements. "
    "Do not drop a required property or relationship to make the selection smaller. "
    "Do not select unrelated concepts. Return candidate IDs only."
)


def candidate_options(candidates, index):
    return [{
        "id": c["id"],
        "name": c["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1],
        "kind": index[c["uri"]].get("kind"),
        "label": index[c["uri"]].get("label"),
        "description": index[c["uri"]].get("description"),
    } for c in candidates]


def run_strategy(strategy, question, candidates, index, args):
    options = candidate_options(candidates, index)
    messages = [{"role": "system", "content": SYSTEM}]
    elapsed = 0.0
    calls = []
    requirements = None
    if strategy == "two_stage":
        first, secs, usage = ask(args.ollama_url, args.model, [
            {"role": "system", "content": "You analyze engineering questions. Return schema-valid JSON only."},
            {"role": "user", "content": json.dumps({
                "question": question, "instruction": STAGE1,
            }, ensure_ascii=False)}
        ], REQUIREMENTS_SCHEMA, args.timeout, args.seed, args.num_ctx)
        requirements = first["information_requirements"]
        if not isinstance(requirements, list) or any(not isinstance(x, str) for x in requirements):
            raise ValueError("Invalid information requirements response")
        elapsed += secs
        calls.append(usage)
        instruction = STAGE2
    else:
        instruction = MINIMAL if strategy == "minimal" else RECALL
    user = {"question": question, "candidates": options, "instruction": instruction}
    if requirements is not None:
        user["information_requirements"] = requirements
    parsed, secs, usage = ask(args.ollama_url, args.model, messages + [
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
    ], IDS_SCHEMA, args.timeout, args.seed, args.num_ctx)
    elapsed += secs
    calls.append(usage)
    ids = parsed["selected_candidate_ids"]
    valid = {c["id"] for c in candidates}
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(
            type(x) is not int or x not in valid for x in ids):
        raise ValueError(f"Invalid selected candidate IDs: {ids!r}")
    selected = [c["uri"] for c in candidates if c["id"] in ids]
    return selected, requirements, round(elapsed, 3), calls


def aggregate(rows, strategy):
    complete = [r["strategies"][strategy] for r in rows if strategy in r["strategies"]]
    if not complete:
        return None
    cm = [r["concept_metrics"] for r in complete]
    dm = [r["domain_metrics"] for r in complete]
    n = len(cm)
    return {
        "cases": n,
        "macro_concept_precision": sum(m["precision"] for m in cm) / n,
        "macro_concept_recall": sum(m["recall"] for m in cm) / n,
        "complete_concept_coverage": sum(m["complete_coverage"] for m in cm),
        "macro_domain_f1": sum(m["f1"] for m in dm) / n,
        "domain_exact": sum(m["exact"] for m in dm),
        "total_latency_seconds": sum(r["latency_seconds"] for r in complete),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=HERE / "data/benchmark_15.json")
    ap.add_argument("--reviewed", type=Path, default=HERE / "data/reviewed_concepts_6.json")
    ap.add_argument("--retrieval", type=Path, default=HERE / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=HERE / "data/ollama_prompt_ablation_29.json")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--mode", choices=["lexical", "vector", "hybrid"], default="hybrid")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--strategies", nargs="+", choices=["minimal", "recall", "two_stage"],
                    default=["minimal", "recall", "two_stage"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.top_k < 1 or args.limit < 0 or args.timeout < 1 or args.num_ctx < 256:
        ap.error("Invalid top-k, limit, timeout or num-ctx")
    if len(set(args.strategies)) != len(args.strategies):
        ap.error("Duplicate strategies")
    common = load("exp28", "28_evaluate_llm_concept_selection.py")
    policy = load("concept_role_policy", "concept_role_policy.py")
    exp25 = load("exp25", "25_evaluate_ontology_resolved_domains.py")
    index_data, benchmark, reviewed, retrieval = [
        read(p) for p in (args.index, args.benchmark, args.reviewed, args.retrieval)]
    index = {c["uri"]: c for c in index_data["concepts"] if c.get("uri")}
    mapping = exp25.resolver(index_data)
    questions = {c["id"]: c for c in benchmark["cases"]}
    hits = {r["id"]: r for r in retrieval["results"]}
    cases = reviewed["cases"][:args.limit or None]
    if len(questions) != len(benchmark["cases"]) or len(hits) != len(retrieval["results"]):
        raise ValueError("Duplicate benchmark/retrieval IDs")
    if any(c["id"] not in questions or c["id"] not in hits for c in cases):
        raise ValueError("Reviewed question missing from benchmark/retrieval")
    input_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
        ("index", args.index), ("benchmark", args.benchmark),
        ("reviewed", args.reviewed), ("retrieval", args.retrieval))}
    rows = []
    for case in cases:
        qid = case["id"]
        candidates = common.candidate_set(hits[qid][args.mode]["hits"], args.top_k, index)
        gold = [c["uri"] for c in case["required"]]
        if any(uri not in index for uri in gold):
            raise ValueError(f"Gold concept URI absent from ontology: {qid}")
        ceiling = common.concept_metrics(gold, [c["uri"] for c in candidates])
        row = {"id": qid, "question": questions[qid]["question"],
               "candidate_uris": [c["uri"] for c in candidates],
               "topk_baseline": ceiling, "strategies": {}}
        rows.append(row)
        if args.dry_run:
            print(f"{qid}: candidates={len(candidates)} gold-in-topk={ceiling['matched']}/{len(gold)}")
        else:
            for strategy in args.strategies:
                selected, requirements, seconds, usage = run_strategy(
                    strategy, row["question"], candidates, index, args)
                evidence = [u for u in selected if policy.eligible_for_domain_evidence(u)]
                linking = [u for u in selected if not policy.eligible_for_domain_evidence(u)]
                domains = sorted({next(iter(mapping[u])) for u in evidence
                                  if len(mapping.get(u, ())) == 1})
                cm = common.concept_metrics(gold, selected)
                row["strategies"][strategy] = {
                    "selected_uris": selected,
                    "missed_required_uris": sorted(set(gold) - set(selected)),
                    "extra_selected_uris": sorted(set(selected) - set(gold)),
                    "information_requirements": requirements,
                    "domain_evidence_uris": evidence, "graph_linking_uris": linking,
                    "predicted_domains": domains,
                    "concept_metrics": cm,
                    "domain_metrics": exp25.metrics(
                        questions[qid]["expected_domains"], domains),
                    "latency_seconds": seconds, "calls": usage,
                }
                print(f"{qid:3} {strategy:9} precision={cm['precision']:.3f} "
                      f"recall={cm['recall']:.3f} complete={cm['complete_coverage']} "
                      f"missed={len(row['strategies'][strategy]['missed_required_uris'])} "
                      f"domains={domains} time={seconds:.1f}s", flush=True)
                save(args, rows, input_hashes)
        save(args, rows, input_hashes)
    if not args.dry_run:
        print("\nSummary (macro means over reviewed cases):")
        for strategy in args.strategies:
            s = aggregate(rows, strategy)
            if s:
                print(f"{strategy:9} P={s['macro_concept_precision']:.3f} "
                      f"R={s['macro_concept_recall']:.3f} "
                      f"complete={s['complete_concept_coverage']}/{s['cases']} "
                      f"domain-F1={s['macro_domain_f1']:.3f} "
                      f"domain-exact={s['domain_exact']}/{s['cases']} "
                      f"latency={s['total_latency_seconds']:.1f}s")
    print("Saved:", args.output)


def save(args, rows, hashes):
    report = {
        "experiment": "29_ollama_prompt_ablation", "model": args.model,
        "mode": args.mode, "top_k": args.top_k,
        "strategies": args.strategies, "seed": args.seed,
        "temperature": 0, "num_ctx": args.num_ctx,
        "dry_run": args.dry_run, "completed_cases": len(rows),
        "input_sha256": hashes,
        "summary": {s: aggregate(rows, s) for s in args.strategies},
        "results": rows,
        "limitations": [
            "Six reviewed questions only; exploratory prompt comparison, no untouched holdout.",
            "The same frozen retrieval candidates are used for every strategy.",
            "Candidate ceiling bounds recall; top-10 hybrid may use fusion weight 0.70.",
            "Two-stage uses two model calls, so latency is not directly comparable per call.",
            "Model-derived requirements are not gold annotations.",
            "Graph-linking identifiers never vote for domains; graph traversal is not executed.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
