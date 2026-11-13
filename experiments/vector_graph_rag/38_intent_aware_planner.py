"""Experiment 38: fail-closed intent and path guard for Experiment 36D.

Two modes:
  --replay-report FILE: re-evaluate saved Experiment 37 selections without LLM
  --question TEXT: run the existing 36D planner, then guard its selection
No GraphDB request occurs unless --execute is passed in live mode.
Replay results are post-hoc and must NOT be reported as independent accuracy.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"

def load(name, file):
    spec = spec_from_file_location(name, HERE / file)
    m = module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

def normalize(s):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))

def local(uri):
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]

def intent(question):
    q = question.lower()
    # Conservative routing: temporal questions are not answerable by static SPARQL.
    temporal = (re.search(r"\b(last|past|previous|next)\s+\d*\s*(hour|minute|second|day|week)s?\b", q)
                or re.search(r"\b(average|mean|trend|time.series|observations?|historical|timescale|vtkg)\b", q)
                or re.search(r"\bbetween\b.*\b(and|to)\b.*\b(seconds?|minutes?|hours?)\b", q))
    if temporal:
        return "temporal_requires_vtkg"
    if re.search(r"\b(cross.domain|across domains|between domains|join.*\b(ecad|asset inventory|dexpi|bom)\b)\b", q):
        return "cross_domain_unsupported"
    if re.search(r"\b(delete|drop|insert|update|clear|remove|erase|modify)\b.*\b(triples?|graph|repository|records?|data)\b", q):
        return "mutation_unsupported"
    if re.search(r"\b(passwords?|secrets?|credentials?|api.keys?|private.keys?)\b", q):
        return "sensitive_unsupported"
    if re.search(r"\b(weather|forecast|football|stock price)\b", q):
        return "outside_ontology"
    return "static_candidate"

def explicit_sequence(question):
    # Only treat a precisely specified ordered sequence as an exact constraint.
    m = re.search(r"follow the nested relationships\s+(.+?)\.\s*which resources", question, re.I)
    if not m:
        return None
    parts = re.split(r"\s+then\s+", m.group(1), flags=re.I)
    return [normalize(p) for p in parts] if 2 <= len(parts) <= 3 else None

def domain_hint(question, domains):
    # Only explicit 'in the DOMAIN model' hints are binding.
    m = re.search(r"\bin the\s+([a-z][a-z0-9_-]*)\s+model\b", question, re.I)
    if not m:
        return None
    return m.group(1).lower() if m.group(1).lower() in domains else "UNKNOWN_DOMAIN"

def guard(question, proposed_id, docs):
    """Return decision, selected ID and evidence. Never trusts proposed URI/SPARQL."""
    paths = {d["uri"]: d for d in docs}
    kind = intent(question)
    if kind != "static_candidate":
        return {"status": "abstained", "reason": kind, "selected_path_id": "ABSTAIN",
                "proposed_path_id": proposed_id}
    sequence = explicit_sequence(question)
    domains = {d["domain"] for d in docs}
    hint = domain_hint(question, domains)
    if hint == "UNKNOWN_DOMAIN":
        return {"status": "abstained", "reason": "unknown_explicit_domain",
                "selected_path_id": "ABSTAIN", "proposed_path_id": proposed_id}
    if sequence:
        matches = [d for d in docs if
                   [normalize(local(p)) for p in d["path"]["predicates"]] == sequence
                   and (hint is None or d["domain"] == hint)]
        if len(matches) != 1:
            return {"status": "abstained", "reason": "explicit_sequence_not_unique_or_missing",
                    "selected_path_id": "ABSTAIN", "proposed_path_id": proposed_id,
                    "matching_paths": len(matches)}
        # The exact path constraint is deterministic, irrespective of LLM ranking.
        return {"status": "selected", "reason": "unique_explicit_sequence",
                "selected_path_id": matches[0]["uri"],
                "proposed_path_id": proposed_id,
                "corrected_llm_choice": proposed_id != matches[0]["uri"]}
    if proposed_id == "ABSTAIN":
        return {"status": "abstained", "reason": "llm_abstained",
                "selected_path_id": "ABSTAIN", "proposed_path_id": proposed_id}
    if proposed_id not in paths:
        return {"status": "abstained", "reason": "unknown_proposed_path",
                "selected_path_id": "ABSTAIN", "proposed_path_id": proposed_id}
    selected = paths[proposed_id]
    if hint is not None and selected["domain"] != hint:
        return {"status": "abstained", "reason": "domain_mismatch",
                "selected_path_id": "ABSTAIN", "proposed_path_id": proposed_id}
    # Natural-language semantic entailment is NOT proven by these checks.
    return {"status": "selected", "reason": "catalog_candidate_unverified_semantics",
            "selected_path_id": proposed_id, "proposed_path_id": proposed_id,
            "semantic_verification": "not_established"}

def replay(source, docs):
    if source.get("experiment") != 37 or source.get("stage") != "planning":
        raise ValueError("Expected Experiment 37 planning report")
    results = []
    for case in source["cases"]:
        proposed = case.get("selected_path_id")
        if proposed is None or case.get("status") != "evaluated":
            results.append({"id": case["id"], "status": "not_evaluated"})
            continue
        decision = guard(case["question"], proposed, docs)
        results.append({"id": case["id"], "kind": case["kind"],
                        "expected_path_id": case["expected_path_id"],
                        "old_selected_path_id": proposed, **decision,
                        "correct": decision["selected_path_id"] == case["expected_path_id"]})
    valid = [r for r in results if r.get("correct") is not None]
    pos = [r for r in valid if r["kind"] == "positive"]
    neg = [r for r in valid if r["kind"] == "unsupported"]
    return {"experiment": 38, "mode": "posthoc_replay",
            "caveat": "Same catalog-derived cases used to design safeguards; not held-out or fresh LLM evaluation",
            "source_index_sha256": source.get("index_sha256"),
            "metrics": {
                "evaluated": len(valid),
                "positive_correct": sum(x["correct"] for x in pos),
                "positive_total": len(pos),
                "negative_correct_abstentions": sum(x["correct"] for x in neg),
                "negative_total": len(neg),
                "changed_decisions": sum(r["selected_path_id"] != r["old_selected_path_id"] for r in valid),
                "still_wrong": [r["id"] for r in valid if not r["correct"]]
            }, "cases": results}

def self_test(docs):
    assert docs
    for doc in docs:
        seq = " then ".join(normalize(local(u)) for u in doc["path"]["predicates"])
        q = f"In the {doc['domain']} model, follow the nested relationships {seq}. Which resources are connected?"
        decision = guard(q, "ABSTAIN", docs)
        assert decision["selected_path_id"] == doc["uri"], (doc["uri"], decision)
    for q, expected in [
        ("What is the average temperature during the last hour for TI_101?", "temporal_requires_vtkg"),
        ("Find a verified cross-domain join between asset inventory and ECAD devices.", "cross_domain_unsupported"),
        ("Delete all triples in the repository.", "mutation_unsupported"),
        ("Show the private administrator password.", "sensitive_unsupported"),
        ("What is the weather forecast for tomorrow?", "outside_ontology"),
    ]:
        assert guard(q, docs[0]["uri"], docs)["reason"] == expected
    assert guard("In the productcatalog model, follow the nested relationships invented then fake. Which resources are connected?", docs[0]["uri"], docs)["status"] == "abstained"
    print(json.dumps({"self_test": "passed", "catalog_paths_checked": len(docs),
                      "negative_intent_checks": 5}))

def live(args, docs, compiler, planner):
    # Invoke the existing retrieval + Llama pipeline, without executing it.
    # It writes a separate intermediate report, which is preserved for audit.
    intermediate = args.output.with_name("ontology_38_unfiltered_planner.json")
    import argparse as _argparse
    options = _argparse.Namespace(question=args.question, index=args.index,
                                  output=intermediate, ollama_url=args.ollama_url,
                                  embedding_model=args.embedding_model, model=args.model,
                                  endpoint=args.endpoint, top_k=args.top_k,
                                  vector_weight=args.vector_weight, limit=args.limit,
                                  timeout=args.timeout, inspect=False, self_test=False,
                                  execute=False)
    # Avoid even calling the LLM for clearly unsupported intents.
    if intent(args.question) != "static_candidate":
        proposal = "ABSTAIN"
        raw = None
    else:
        planner.run(options)
        raw = read(intermediate)
        proposal = raw["selected_path_id"]
    decision = guard(args.question, proposal, docs)
    report = {"experiment": 38, "mode": "live", "question": args.question,
              "intent": intent(args.question), **decision,
              "execution": "not_requested", "llm_planner_report": str(intermediate) if raw else None}
    if decision["status"] == "selected":
        doc = next(d for d in docs if d["uri"] == decision["selected_path_id"])
        compiled = compiler.compile_plan(
            {"operation": "nested_path_select",
             "predicates": doc["path"]["predicates"], "limit": args.limit}, read(args.index))
        report.update({"query": compiled["query"], "path_evidence": compiled["path_evidence"]})
        if args.execute:
            exp32 = load("exp38_graphdb", "32_execute_simple_sparql.py")
            bindings = exp32.execute(args.endpoint, compiled["query"], args.timeout)
            report.update({"execution": "ok", "returned_rows": len(bindings),
                           "sample_bindings": bindings[:3]})
    save(args.output, report)
    print(json.dumps({"status": report["status"], "reason": report["reason"],
                      "selected_path_id": report["selected_path_id"],
                      "query": report.get("query"), "execution": report["execution"],
                      "returned_rows": report.get("returned_rows"),
                      "output": str(args.output)}, indent=2))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--replay-report", type=Path)
    ap.add_argument("--question")
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_intent_guard_38_results.json")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--embedding-model", default="nomic-embed-text:latest")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--vector-weight", type=float, default=0.75)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.top_k <= 26 or not 0 <= args.vector_weight <= 1 or not 1 <= args.limit <= 100 or args.timeout < 1:
        ap.error("Invalid top-k, vector-weight, limit or timeout")
    if args.execute and (args.replay_report or args.self_test):
        ap.error("--execute is only available with --question")
    compiler = load("exp38_compiler", "36_multihop_planner.py")
    planner = load("exp38_planner", "36_nl_multihop.py")
    docs = planner.path_documents(read(args.index), compiler)
    if args.self_test:
        self_test(docs)
    elif args.replay_report:
        source = read(args.replay_report)
        if source.get("index_sha256") != hashlib.sha256(args.index.read_bytes()).hexdigest():
            raise ValueError("Benchmark and current ontology index SHA256 differ")
        result = replay(source, docs)
        save(args.output, result)
        print(json.dumps({"mode": "posthoc_replay", "metrics": result["metrics"],
                          "output": str(args.output)}, indent=2))
    elif args.question:
        live(args, docs, compiler, planner)
    else:
        ap.error("Choose --self-test, --replay-report FILE or --question TEXT")

if __name__ == "__main__":
    main()
