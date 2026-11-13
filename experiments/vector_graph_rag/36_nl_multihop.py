"""Experiment 36D: hybrid retrieval + Llama path selection + validated multi-hop SPARQL.

LLM chooses only a catalog path ID or abstains. No LLM-generated SPARQL is
executed. GraphDB execution is opt-in; returned rows do not establish answer
correctness.

 python experiments/vector_graph_rag/36_nl_multihop.py --inspect
 python experiments/vector_graph_rag/36_nl_multihop.py --self-test
 python experiments/vector_graph_rag/36_nl_multihop.py --question "Which individual assets are in the asset inventory?"
 python experiments/vector_graph_rag/36_nl_multihop.py --question "Which individual assets are in the asset inventory?" --execute
"""
import argparse
import hashlib
import json
import re
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"

def load_module(name, filename):
    spec = spec_from_file_location(name, HERE / filename)
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def path_documents(index, compiler):
    properties, _ = compiler.catalog(index)
    paths = compiler.candidate_paths(index)
    documents = []
    for path in paths:
        labels = []
        for uri in path["predicates"]:
            prop = properties[uri]
            labels.append(" ".join(prop.get("labels", []) + prop.get("descriptions", [])))
        doc = "Domain: " + path["domain"] + ". Nested relationship chain: " + " then ".join(labels)
        documents.append({"uri": "path:" + hashlib.sha256(
            json.dumps(path, sort_keys=True).encode()).hexdigest()[:16],
            "path": path, "labels": labels, "text": doc,
            "domain": path["domain"], "kind": "property",
            "descriptions": [doc]})
    return documents

def parse_choice(raw, candidate_ids):
    response = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", response, re.I | re.S)
    if fenced:
        response = fenced.group(1)
    choice = json.loads(response)
    if not isinstance(choice, dict) or set(choice) != {"path_id"}:
        raise ValueError("LLM must return only path_id")
    path_id = choice["path_id"]
    if path_id != "ABSTAIN" and path_id not in candidate_ids:
        raise ValueError("LLM selected an unlisted path ID")
    return path_id

def self_test(index, compiler):
    docs = path_documents(index, compiler)
    assert docs, "No evidence-supported paths in ontology"
    assert len({d["uri"] for d in docs}) == len(docs)
    selected = docs[0]
    plan = {"operation": "nested_path_select",
            "predicates": selected["path"]["predicates"], "limit": 10}
    compiled = compiler.compile_plan(plan, index)
    assert compiled["status"] == "compiled"
    assert parse_choice(json.dumps({"path_id": selected["uri"]}), {selected["uri"]}) == selected["uri"]
    assert parse_choice('{"path_id":"ABSTAIN"}', {selected["uri"]}) == "ABSTAIN"
    for invalid in ['{"path_id":"path:invented"}',
                    '{"path_id":"ABSTAIN","query":"DELETE WHERE {}"}',
                    '{"path_id":12}']:
        try:
            parse_choice(invalid, {selected["uri"]})
        except (ValueError, TypeError):
            continue
        raise AssertionError("Accepted invalid LLM output")
    print(f"Self-test passed: {len(docs)} catalog paths, validated compilation and fail-closed LLM choices")

def run(args):
    compiler = load_module("exp36d_multihop", "36_multihop_planner.py")
    exp30 = load_module("exp36d_retrieval", "30_evaluate_simple_questions.py")
    exp33 = load_module("exp36d_llm", "33_llm_sparql.py")
    index = read(args.index)
    docs = path_documents(index, compiler)
    if not docs:
        raise ValueError("No SHACL-evidenced multi-hop paths")
    if args.inspect:
        print(json.dumps({"catalog_paths": len(docs),
                          "examples": [{"path_id": d["uri"], **d["path"]} for d in docs[:10]]}, indent=2))
        return
    if args.self_test:
        self_test(index, compiler)
        return
    if not args.question:
        raise ValueError("--question is required")
    sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    cache = args.output.with_name("ontology_multihop_36_embedding_cache.json")
    uris = [d["uri"] for d in docs]
    cached = read(cache) if cache.exists() else {}
    if (cached.get("index_sha256") == sha and
        cached.get("model") == args.embedding_model and
        cached.get("uris") == uris and cached.get("texts") == [d["text"] for d in docs]):
        vectors = cached["vectors"]
    else:
        vectors = exp30.embed(args.ollama_url, args.embedding_model,
                              [d["text"] for d in docs], args.timeout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"index_sha256": sha, "model": args.embedding_model,
                                     "uris": uris, "texts": [d["text"] for d in docs],
                                     "vectors": vectors}), encoding="utf-8")
    # Lexical ranking uses the same path descriptions as embedding retrieval.
    lex = exp30.lexical_ranking(args.question, docs)
    qvec = exp30.embed(args.ollama_url, args.embedding_model, [args.question], args.timeout)[0]
    vec = exp30.vector_ranking(qvec, vectors, docs)
    ranked = exp30.fusion(lex, vec, docs, args.vector_weight)
    candidates = [docs[i] for i in ranked[:args.top_k]]
    prompt = (
        "You are a constrained ontology path selector. Choose the SINGLE "
        "best path that directly answers the question, or abstain if none "
        "fits. You may ONLY output JSON exactly {\"path_id\":\"ID\"} "
        "where ID is a listed path_id or ABSTAIN. Do not invent predicates, "
        "paths, joins or SPARQL. The path direction and meaning matter.\n"
        "Question: " + args.question + "\nSupported candidate paths:\n" +
        "\n".join(json.dumps({"path_id": d["uri"], "domain": d["domain"],
                               "predicates": d["path"]["predicates"],
                               "meaning": d["text"]}) for d in candidates) +
        "\nReturn only the JSON object."
    )
    start = time.monotonic()
    raw = exp33.ollama(args.ollama_url, args.model, prompt, args.timeout)
    choice = parse_choice(raw, {d["uri"] for d in candidates})
    report = {"experiment": "36D_nl_multihop", "question": args.question,
              "model": args.model, "embedding_model": args.embedding_model,
              "index_sha256": sha, "vector_weight": args.vector_weight,
              "candidate_paths": [{"path_id": d["uri"], **d["path"]} for d in candidates],
              "llm_raw": raw, "selected_path_id": choice,
              "execution": "not_requested"}
    if choice == "ABSTAIN":
        report["status"] = "abstained"
    else:
        chosen = next(d for d in candidates if d["uri"] == choice)
        plan = {"operation": "nested_path_select",
                "predicates": chosen["path"]["predicates"], "limit": args.limit}
        report["plan"] = plan
        report.update(compiler.compile_plan(plan, index))
        if args.execute:
            exp32 = load_module("exp36d_execute", "32_execute_simple_sparql.py")
            bindings = exp32.execute(args.endpoint, report["query"], args.timeout)
            report.update({"execution": "ok", "returned_rows": len(bindings),
                           "nonempty": bool(bindings), "sample_bindings": bindings[:3]})
    report["seconds"] = round(time.monotonic() - start, 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "selected_path_id": choice,
                      "plan": report.get("plan"), "query": report.get("query"),
                      "execution": report["execution"],
                      "returned_rows": report.get("returned_rows"),
                      "output": str(args.output)}, indent=2))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question")
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_nl_multihop_36_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.top_k <= 26 or not 0 <= args.vector_weight <= 1 or not 1 <= args.limit <= 100 or args.timeout < 1:
        ap.error("Invalid top-k, vector-weight, limit or timeout")
    run(args)

if __name__ == "__main__":
    main()
