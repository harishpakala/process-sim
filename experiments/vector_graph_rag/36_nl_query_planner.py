"""Experiment 36B: NL question -> hybrid retrieval -> LLM JSON plan -> validated SPARQL.

Requires local Ollama. The LLM never provides executable SPARQL: only a JSON
plan; the Experiment 36 deterministic compiler validates SHACL evidence.
No graph query is run unless --execute is supplied.

 python experiments/vector_graph_rag/36_nl_query_planner.py --question "Show asset identifiers and names"
 python experiments/vector_graph_rag/36_nl_query_planner.py --question "Show asset identifiers and names" --execute
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

def module(name, filename):
    spec = spec_from_file_location(name, HERE / filename)
    mod = module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def json_response(raw):
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1)
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("LLM response must be a JSON object")
    return obj

def run(args):
    exp30 = module("exp36b_30", "30_evaluate_simple_questions.py")
    exp33 = module("exp36b_33", "33_llm_sparql.py")
    planner = module("exp36b_compiler", "36_ontology_query_planner.py")
    index = read(args.index)
    concepts = sorted((c for c in index["concepts"] if c.get("kind") == "property"
                       and c.get("uri")), key=lambda c: c["uri"])
    uris = [c["uri"] for c in concepts]
    if len(set(uris)) != len(uris):
        raise ValueError("Duplicate ontology property URI")
    sha = hashlib.sha256(args.index.read_bytes()).hexdigest()
    cache = args.output.with_name("ontology_planner_36_embedding_cache.json")
    cached = read(cache) if cache.exists() else {}
    if (cached.get("index_sha256") == sha and
        cached.get("model") == args.embedding_model and cached.get("uris") == uris):
        vectors = cached["vectors"]
    else:
        vectors = exp30.embed(args.ollama_url, args.embedding_model,
                              [exp30.concept_text(c) for c in concepts], args.timeout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"index_sha256": sha, "model": args.embedding_model,
                                     "uris": uris, "vectors": vectors}), encoding="utf-8")
    lex = exp30.lexical_ranking(args.question, concepts)
    qvec = exp30.embed(args.ollama_url, args.embedding_model,
                       [args.question], args.timeout)[0]
    vec = exp30.vector_ranking(qvec, vectors, concepts)
    ranked = exp30.fusion(lex, vec, concepts, args.vector_weight)
    candidate_uris = [uris[i] for i in ranked[:args.top_k]]
    # Enumerate only the pairs supported by the same SHACL node shape.
    _, paths = planner.evidence_catalog(index)
    pairs = {}
    for (domain, shape), available in paths.items():
        selected = [u for u in candidate_uris if u in available]
        for i, first in enumerate(selected):
            for second in selected[i+1:]:
                key = tuple(sorted((first, second)))
                pairs.setdefault(key, []).append({"domain": domain, "node_shape": shape})
    admissible_pairs = []
    for pair, contexts in sorted(pairs.items()):
        if len(contexts) == 1:
            admissible_pairs.append(list(pair))
    prompt = (
        "You are selecting ontology properties for a read-only engineering question. "
        "Return ONLY a JSON object with EXACTLY three keys: operation, predicates, limit. "
        "operation is 'single_select' for one predicate or 'star_select' for two "
        "predicates sharing a subject. Select ONLY from candidate URIs below. "
        "For star_select choose ONLY a pair in admissible_pairs. "
        "Do not invent URIs or operations. limit must be integer 1..100. "
        "No SPARQL, no markdown. If the question cannot be expressed with these "
        "operations, return the JSON object "
        "{\"operation\":\"abstain\",\"predicates\":[],\"limit\":10}.\n"
        "Question: " + args.question + "\n"
        "Candidates (ranked):\n" +
        "\n".join(f"{i+1}. {concepts[idx]['uri']} | " +
                  ", ".join(concepts[idx].get("labels", [])[:2]) +
                  " | " + concepts[idx].get("domain", "")
                  for i, idx in enumerate(ranked[:args.top_k])) +
        "\nAdmissible two-predicate pairs:\n" + json.dumps(admissible_pairs)
    )
    start = time.monotonic()
    raw = exp33.ollama(args.ollama_url, args.model, prompt, args.timeout)
    plan = json_response(raw)
    report = {"experiment": "36_nl_ontology_query_planner",
              "question": args.question, "model": args.model,
              "embedding_model": args.embedding_model,
              "index_sha256": sha, "retrieved_candidate_uris": candidate_uris,
              "admissible_pairs": admissible_pairs, "raw_llm_response": raw,
              "proposed_plan": plan, "execution": "not_requested"}
    if plan.get("operation") == "abstain":
        if set(plan) != {"operation", "predicates", "limit"} or plan["predicates"] != []:
            raise ValueError("Malformed abstention plan")
        report["status"] = "abstained"
    else:
        if any(u not in candidate_uris for u in plan.get("predicates", [])):
            raise planner.PlanRejected("LLM selected a property outside retrieved candidates")
        if plan.get("operation") == "star_select":
            if (not isinstance(plan.get("predicates"), list) or
                sorted(plan["predicates"]) not in admissible_pairs):
                raise planner.PlanRejected("LLM selected a non-admissible pair")
        compiled = planner.compile_plan(plan, index)
        report.update(compiled)
        if args.execute:
            exp32 = module("exp36b_32", "32_execute_simple_sparql.py")
            bindings = exp32.execute(args.endpoint, compiled["query"], args.timeout)
            report.update({"execution": "ok", "returned_rows": len(bindings),
                           "nonempty": bool(bindings), "sample_bindings": bindings[:3]})
    report["seconds"] = round(time.monotonic() - start, 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "plan": plan,
                      "query": report.get("query"), "execution": report["execution"],
                      "returned_rows": report.get("returned_rows"),
                      "output": str(args.output)}, indent=2))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", required=True)
    ap.add_argument("--index", type=Path, default=ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json")
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_nl_planner_36_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if not 2 <= args.top_k <= 30 or not 0 <= args.vector_weight <= 1 or args.timeout < 1:
        ap.error("Invalid top-k, vector-weight or timeout")
    run(args)

if __name__ == "__main__":
    main()
