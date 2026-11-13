"""Controlled evaluation of frozen Experiment 36D: lexical vs vector vs hybrid.

No keyword-based intent rules, no Experiment 38 guard, no database execution.
Supply an independently authored/annotated JSON dataset; do not tune on it.
Each method uses the same path catalog, Llama model, prompt and top-k.
Outputs checkpoint after each question/method and may be resumed.

Example:
 python experiments/vector_graph_rag/39_compare_frozen_pipeline.py --self-test
 python experiments/vector_graph_rag/39_compare_frozen_pipeline.py --dataset experiments/vector_graph_rag/data/independent_questions_39.json
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"

def module(name, filename):
    spec = spec_from_file_location(name, HERE / filename)
    m = module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def dataset_cases(dataset, valid_ids):
    if dataset.get("dataset_type") != "independent_human_annotated":
        raise ValueError("Dataset must declare dataset_type=independent_human_annotated")
    if not dataset.get("annotation_protocol") or not dataset.get("annotation_provenance"):
        raise ValueError("Dataset needs annotation_protocol and annotation_provenance")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must contain at least one labeled case")
    seen = set()
    for c in cases:
        if not isinstance(c, dict) or not all(c.get(k) for k in ("id", "question", "expected_path_id", "annotation_note")):
            raise ValueError("Each case requires id, question, expected_path_id, annotation_note")
        if c["id"] in seen:
            raise ValueError("Duplicate case id: " + c["id"])
        seen.add(c["id"])
        if c["expected_path_id"] != "ABSTAIN" and c["expected_path_id"] not in valid_ids:
            raise ValueError("Unknown gold path: " + c["expected_path_id"])
    return cases

def prompt(question, candidates):
    # Match Experiment 37's frozen constrained selector prompt.
    return (
        "You are a constrained ontology path selector. Choose the SINGLE "
        "best path that directly answers the question, or abstain if none fits. "
        "You may ONLY output JSON exactly {\"path_id\":\"ID\"} where ID "
        "is a listed path_id or ABSTAIN. Never invent predicates, paths, "
        "joins or SPARQL. Follow path direction.\nQuestion: " +
        question + "\nSupported candidate paths:\n" +
        "\n".join(json.dumps({"path_id": d["uri"], "domain": d["domain"],
                               "predicates": d["path"]["predicates"],
                               "meaning": d["text"]}) for d in candidates) +
        "\nReturn only the JSON object."
    )

def summarize(report):
    cases = report["cases"]
    summary = {}
    for method in ("lexical", "vector", "hybrid"):
        pos = [c for c in cases if c["expected_path_id"] != "ABSTAIN"]
        neg = [c for c in cases if c["expected_path_id"] == "ABSTAIN"]
        evaluated = [c for c in cases if c["methods"].get(method, {}).get("status") == "evaluated"]
        pos_eval = [c for c in evaluated if c["expected_path_id"] != "ABSTAIN"]
        neg_eval = [c for c in evaluated if c["expected_path_id"] == "ABSTAIN"]
        summary[method] = {
            "retrieval_positive_total": len(pos),
            "recall_at_1": sum(c["methods"].get(method, {}).get("gold_rank") == 1 for c in pos) / len(pos) if pos else None,
            "recall_at_5": sum(0 < (c["methods"].get(method, {}).get("gold_rank") or 0) <= 5 for c in pos) / len(pos) if pos else None,
            "recall_at_k": sum(0 < (c["methods"].get(method, {}).get("gold_rank") or 0) <= report["configuration"]["top_k"] for c in pos) / len(pos) if pos else None,
            "planning_evaluated": len(evaluated),
            "planning_errors_or_pending": len(cases) - len(evaluated),
            "positive_path_accuracy": sum(c["methods"][method]["correct"] for c in pos_eval) / len(pos_eval) if pos_eval else None,
            "negative_abstention_rate": sum(c["methods"][method]["correct"] for c in neg_eval) / len(neg_eval) if neg_eval else None,
            "false_abstentions": sum(c["methods"][method]["selected_path_id"] == "ABSTAIN" for c in pos_eval),
            "false_unsupported_selections": sum(c["methods"][method]["selected_path_id"] != "ABSTAIN" for c in neg_eval),
            "total_correct": sum(c["methods"][method]["correct"] for c in evaluated),
            "total_evaluated": len(evaluated),
        }
    return summary

def self_test():
    docs = [{"uri": "path:a", "domain": "a", "path": {"predicates": ["urn:a"]}, "text": "a"},
            {"uri": "path:b", "domain": "b", "path": {"predicates": ["urn:b"]}, "text": "b"}]
    cases = dataset_cases({"dataset_type": "independent_human_annotated",
                           "annotation_protocol": "manual",
                           "annotation_provenance": "test",
                           "cases": [{"id": "A", "question": "Example?", "expected_path_id": "path:a", "annotation_note": "test"},
                                     {"id": "B", "question": "Unsupported?", "expected_path_id": "ABSTAIN", "annotation_note": "test"}]},
                          {d["uri"] for d in docs})
    report = {"configuration": {"top_k": 1}, "cases": [
        {**cases[0], "methods": {m: {"status": "evaluated", "gold_rank": 1,
                                     "selected_path_id": "path:a", "correct": True} for m in ("lexical", "vector", "hybrid")}},
        {**cases[1], "methods": {m: {"status": "evaluated", "gold_rank": None,
                                     "selected_path_id": "ABSTAIN", "correct": True} for m in ("lexical", "vector", "hybrid")}}]}
    assert summarize(report)["hybrid"]["total_correct"] == 2
    assert summarize(report)["hybrid"]["negative_abstention_rate"] == 1
    assert "\"path_id\"" in prompt("Example?", docs)
    print(json.dumps({"self_test": "passed", "methods": 3, "no_execution": True}))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--output", type=Path, default=HERE / "data/frozen_comparison_39_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.dataset:
        ap.error("--dataset is required (no synthetic benchmark questions are generated)")
    if not 1 <= args.top_k <= 26 or not 0 <= args.vector_weight <= 1 or args.timeout < 1:
        ap.error("Invalid top-k, vector-weight or timeout")
    compiler = module("exp39_compiler", "36_multihop_planner.py")
    planner = module("exp39_planner", "36_nl_multihop.py")
    retrieval = module("exp39_retrieval", "30_evaluate_simple_questions.py")
    llm = None if args.retrieval_only else module("exp39_llm", "33_llm_sparql.py")
    docs = planner.path_documents(read(args.index), compiler)
    cases = dataset_cases(read(args.dataset), {d["uri"] for d in docs})
    index_sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    dataset_sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    config = {"top_k": args.top_k, "vector_weight": args.vector_weight,
              "model": args.model, "embedding_model": args.embedding_model,
              "index_sha256": index_sha, "dataset_sha256": dataset_sha,
              "retrieval_only": args.retrieval_only}
    if args.output.exists() and not args.overwrite:
        report = read(args.output)
        if report.get("configuration") != config or [c["id"] for c in report["cases"]] != [c["id"] for c in cases]:
            raise ValueError("Existing report configuration/dataset differs; choose new --output or --overwrite")
    else:
        report = {"experiment": 39, "purpose": "frozen Experiment 36D controlled comparison",
                  "dataset_type": "independent_human_annotated (declared; not independently verified)",
                  "configuration": config, "cases": [{**c, "methods": {}} for c in cases],
                  "metrics": {}}
        write(args.output, report)
    cache = args.output.with_name("ontology_multihop_36_embedding_cache.json")
    texts = [d["text"] for d in docs]
    uris = [d["uri"] for d in docs]
    cached = read(cache) if cache.exists() else {}
    if cached.get("index_sha256") == index_sha and cached.get("model") == args.embedding_model and cached.get("uris") == uris and cached.get("texts") == texts:
        vectors = cached["vectors"]
    else:
        vectors = retrieval.embed(args.ollama_url, args.embedding_model, texts, args.timeout)
        write(cache, {"index_sha256": index_sha, "model": args.embedding_model,
                      "uris": uris, "texts": texts, "vectors": vectors})
    for i, case in enumerate(cases):
        row = report["cases"][i]
        lex = retrieval.lexical_ranking(case["question"], docs)
        qvec = retrieval.embed(args.ollama_url, args.embedding_model, [case["question"]], args.timeout)[0]
        vec = retrieval.vector_ranking(qvec, vectors, docs)
        hyb = retrieval.fusion(lex, vec, docs, args.vector_weight)
        for method, order in (("lexical", lex), ("vector", vec), ("hybrid", hyb)):
            old = row["methods"].get(method, {})
            if old.get("status") in ("evaluated", "retrieval_only"):
                continue
            ordered_ids = [docs[j]["uri"] for j in order]
            gold = case["expected_path_id"]
            rank = ordered_ids.index(gold) + 1 if gold != "ABSTAIN" else None
            candidates = [docs[j] for j in order[:args.top_k]]
            result = {"gold_rank": rank, "candidate_path_ids": [d["uri"] for d in candidates]}
            if args.retrieval_only:
                result["status"] = "retrieval_only"
            else:
                start = time.monotonic()
                try:
                    raw = llm.ollama(args.ollama_url, args.model, prompt(case["question"], candidates), args.timeout)
                    choice = planner.parse_choice(raw, set(result["candidate_path_ids"]))
                    result.update({"status": "evaluated", "selected_path_id": choice,
                                   "correct": choice == gold, "llm_raw": raw})
                except Exception as exc:
                    result.update({"status": "error", "error": str(exc)})
                result["planning_seconds"] = round(time.monotonic() - start, 2)
            row["methods"][method] = result
            report["metrics"] = summarize(report)
            write(args.output, report)
            print(f'{case["id"]} {method}: {result["status"]} {result.get("selected_path_id", "")}', flush=True)
    print(json.dumps({"metrics": report["metrics"], "output": str(args.output)}, indent=2))

if __name__ == "__main__":
    main()
