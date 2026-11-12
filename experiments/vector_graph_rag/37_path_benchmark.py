"""Experiment 37: reproducible development benchmark for ontology multi-hop planning.

Cases are programmatically derived from the current SHACL path catalog and
therefore are NOT held-out, independently annotated natural-language cases.
Use --stage retrieval for retrieval metrics without LLM calls, --stage planning
for retrieval + constrained Llama selection, --execute for optional GraphDB
execution of compiled predictions.

 python experiments/vector_graph_rag/37_path_benchmark.py --stage retrieval
 python experiments/vector_graph_rag/37_path_benchmark.py --stage planning
 python experiments/vector_graph_rag/37_path_benchmark.py --stage planning --execute
 python experiments/vector_graph_rag/37_path_benchmark.py --self-test
"""
import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"

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
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def local(uri):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", uri.rsplit("/", 1)[-1])

def make_cases(docs):
    cases = []
    for i, doc in enumerate(docs):
        predicates = doc["path"]["predicates"]
        names = [local(uri) for uri in predicates]
        cases.append({
            "id": f"P{i+1:02d}", "kind": "positive",
            "question": "In the " + doc["domain"] + " model, follow the nested relationships " +
                        " then ".join(names) + ". Which resources are connected?",
            "expected_path_id": doc["uri"], "expected_predicates": predicates,
            "domain": doc["domain"], "source": "generated_from_catalog",
        })
    for i, question in enumerate([
        "Delete all triples in the repository.",
        "What is the weather forecast for tomorrow?",
        "Show the private administrator password.",
        "What is the average temperature during the last hour for TI_101?",
        "Find a verified cross-domain join between asset inventory and ECAD devices."
    ], 1):
        cases.append({"id": f"N{i:02d}", "kind": "unsupported",
                      "question": question, "expected_path_id": "ABSTAIN",
                      "expected_predicates": [], "domain": None,
                      "source": "authored_negative_development_case"})
    return cases

def rank_cases(cases, docs, exp30, vectors, args):
    rows = []
    for case in cases:
        lex = exp30.lexical_ranking(case["question"], docs)
        vec = exp30.vector_ranking(
            exp30.embed(args.ollama_url, args.embedding_model,
                        [case["question"]], args.timeout)[0], vectors, docs)
        hyb = exp30.fusion(lex, vec, docs, args.vector_weight)
        ranks = {}
        for name, ordering in (("lexical", lex), ("vector", vec), ("hybrid", hyb)):
            ids = [docs[i]["uri"] for i in ordering]
            gold = case["expected_path_id"]
            ranks[name] = (ids.index(gold) + 1) if gold != "ABSTAIN" else None
        rows.append({"case": case, "ranks": ranks,
                     "candidate_ids": [docs[i]["uri"] for i in hyb[:args.top_k]]})
    return rows

def metrics(rows, predictions=None):
    positives = [r for r in rows if r["case"]["kind"] == "positive"]
    negatives = [r for r in rows if r["case"]["kind"] == "unsupported"]
    retrieval = {}
    for method in ("lexical", "vector", "hybrid"):
        retrieval[method] = {
            "positive_count": len(positives),
            "recall_at_1": sum(r["ranks"][method] == 1 for r in positives) / len(positives) if positives else None,
            "recall_at_5": sum(r["ranks"][method] is not None and r["ranks"][method] <= 5 for r in positives) / len(positives) if positives else None,
            "recall_at_k": sum(r["ranks"][method] is not None and r["ranks"][method] <= len(r["candidate_ids"]) for r in positives) / len(positives) if positives else None,
        }
    result = {"retrieval": retrieval}
    if predictions is not None:
        evaluated = [p for p in predictions if p.get("status") not in ("error", "not_run")]
        pos = [p for p in evaluated if p["kind"] == "positive"]
        neg = [p for p in evaluated if p["kind"] == "unsupported"]
        result["planning"] = {
            "evaluated": len(evaluated), "errors": len(predictions) - len(evaluated),
            "positive_evaluated": len(pos), "negative_evaluated": len(neg),
            "positive_path_accuracy": sum(p["correct"] for p in pos) / len(pos) if pos else None,
            "negative_abstention_rate": sum(p["correct"] for p in neg) / len(neg) if neg else None,
            "false_abstentions_on_positives": sum(p["selected_path_id"] == "ABSTAIN" for p in pos),
            "false_selections_on_negatives": sum(p["selected_path_id"] != "ABSTAIN" for p in neg),
            "graphdb_execution_ok": sum(p.get("execution") == "ok" for p in evaluated),
            "graphdb_execution_errors": sum(p.get("execution") == "error" for p in evaluated),
            "graphdb_nonempty": sum(p.get("returned_rows", 0) > 0 for p in evaluated),
        }
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("retrieval", "planning"), default="retrieval")
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_path_benchmark_37_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--max-cases", type=int, default=0)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.top_k <= 26 or not 0 <= args.vector_weight <= 1 or not 1 <= args.limit <= 100 or args.timeout < 1 or args.max_cases < 0:
        ap.error("Invalid top-k, vector-weight, limit, timeout or max-cases")
    if args.execute and args.stage != "planning":
        ap.error("--execute requires --stage planning")
    compiler = module("exp37_compiler", "36_multihop_planner.py")
    planner = module("exp37_planner", "36_nl_multihop.py")
    exp30 = module("exp37_retrieval", "30_evaluate_simple_questions.py")
    index = read(args.index)
    docs = planner.path_documents(index, compiler)
    cases = make_cases(docs)
    if args.self_test:
        assert len(cases) == len(docs) + 5
        assert len({d["uri"] for d in docs}) == len(docs)
        for case in cases:
            if case["kind"] == "positive":
                compiler.compile_plan({"operation": "nested_path_select",
                                       "predicates": case["expected_predicates"], "limit": 10}, index)
        assert planner.parse_choice('{"path_id":"ABSTAIN"}', set()) == "ABSTAIN"
        print(json.dumps({"self_test": "passed", "catalog_paths": len(docs),
                          "positive_cases": len(docs), "unsupported_cases": 5}))
        return
    if args.max_cases:
        cases = cases[:args.max_cases]
    sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    cache = args.output.with_name("ontology_multihop_36_embedding_cache.json")
    cached = read(cache) if cache.exists() else {}
    texts = [d["text"] for d in docs]
    uris = [d["uri"] for d in docs]
    if (cached.get("index_sha256") == sha and cached.get("model") == args.embedding_model
        and cached.get("uris") == uris and cached.get("texts") == texts):
        vectors = cached["vectors"]
    else:
        vectors = exp30.embed(args.ollama_url, args.embedding_model, texts, args.timeout)
        write(cache, {"index_sha256": sha, "model": args.embedding_model,
                      "uris": uris, "texts": texts, "vectors": vectors})
    rows = rank_cases(cases, docs, exp30, vectors, args)
    report = {"experiment": 37, "dataset_type": "catalog-derived development benchmark; NOT held-out",
              "index_sha256": sha, "stage": args.stage,
              "configuration": {"top_k": args.top_k, "vector_weight": args.vector_weight,
                                "model": args.model, "embedding_model": args.embedding_model,
                                "execute": args.execute, "max_cases": args.max_cases},
              "catalog_paths": len(docs), "case_count": len(cases),
              "cases": [], "metrics": {}}
    exp33 = module("exp37_llm", "33_llm_sparql.py") if args.stage == "planning" else None
    exp32 = module("exp37_execute", "32_execute_simple_sparql.py") if args.execute else None
    predictions = []
    for row in rows:
        case = row["case"]
        item = {**case, "retrieval_ranks": row["ranks"],
                "candidate_path_ids": row["candidate_ids"]}
        if args.stage == "planning":
            candidates = [next(d for d in docs if d["uri"] == path_id)
                          for path_id in row["candidate_ids"]]
            prompt = (
                "You are a constrained ontology path selector. Choose the SINGLE "
                "best path that directly answers the question, or abstain if none fits. "
                "You may ONLY output JSON exactly {\"path_id\":\"ID\"} where ID "
                "is a listed path_id or ABSTAIN. Never invent predicates, paths, "
                "joins or SPARQL. Follow path direction.\nQuestion: " +
                case["question"] + "\nSupported candidate paths:\n" +
                "\n".join(json.dumps({"path_id": d["uri"], "domain": d["domain"],
                                       "predicates": d["path"]["predicates"],
                                       "meaning": d["text"]}) for d in candidates) +
                "\nReturn only the JSON object."
            )
            started = time.monotonic()
            try:
                raw = exp33.ollama(args.ollama_url, args.model, prompt, args.timeout)
                chosen = planner.parse_choice(raw, set(row["candidate_ids"]))
                item.update({"status": "evaluated", "selected_path_id": chosen,
                             "correct": chosen == case["expected_path_id"],
                             "llm_raw": raw})
                if chosen == "ABSTAIN":
                    item["execution"] = "not_applicable"
                else:
                    doc = next(d for d in candidates if d["uri"] == chosen)
                    compiled = compiler.compile_plan(
                        {"operation": "nested_path_select",
                         "predicates": doc["path"]["predicates"], "limit": args.limit}, index)
                    item.update({"query": compiled["query"], "path_evidence": compiled["path_evidence"],
                                 "execution": "not_requested"})
                    if args.execute:
                        try:
                            bindings = exp32.execute(args.endpoint, compiled["query"], args.timeout)
                            item.update({"execution": "ok", "returned_rows": len(bindings),
                                         "sample_bindings": bindings[:2]})
                        except Exception as exc:
                            item.update({"execution": "error", "execution_error": str(exc)})
            except Exception as exc:
                item.update({"status": "error", "error": str(exc)})
            item["planning_seconds"] = round(time.monotonic() - started, 2)
            predictions.append(item)
        report["cases"].append(item)
        report["metrics"] = metrics(rows, predictions if args.stage == "planning" else None)
        write(args.output, report)  # checkpoint after each case
        print(f'{case["id"]}: ' + (str(item.get("selected_path_id", "retrieval_only"))) +
              (" correct=" + str(item.get("correct")) if args.stage == "planning" else ""),
              flush=True)
    print(json.dumps({"dataset_type": report["dataset_type"],
                      "case_count": len(cases), "metrics": report["metrics"],
                      "output": str(args.output)}, indent=2))

if __name__ == "__main__":
    main()
