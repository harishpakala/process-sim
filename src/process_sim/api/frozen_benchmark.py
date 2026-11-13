"""Experiment 37 single-case UI runner.

Reuses the frozen Experiment 37 case generator, hybrid retrieval, constrained
path selector and deterministic SPARQL compiler. No keyword intent routing.
A successful path selection is NOT a verified natural-language answer.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from process_sim.api.paper_query import ROOT, _load

HERE = ROOT / "experiments/vector_graph_rag"
INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"
_LOCK = threading.Lock()
_CACHE = {}


def _catalog():
    compiler = _load("ui37_compiler", "experiments/vector_graph_rag/36_multihop_planner.py")
    planner = _load("ui37_planner", "experiments/vector_graph_rag/36_nl_multihop.py")
    benchmark = _load("ui37_benchmark", "experiments/vector_graph_rag/37_path_benchmark.py")
    raw = INDEX.read_bytes()
    index = json.loads(raw.decode("utf-8-sig"))
    docs = planner.path_documents(index, compiler)
    cases = benchmark.make_cases(docs)
    digest = hashlib.sha256(raw).hexdigest()
    return compiler, planner, benchmark, index, docs, cases, digest


def questions():
    _, _, _, _, _, cases, digest = _catalog()
    return {"experiment": 37, "indexSha256": digest,
            "provenance": "Catalog-derived development benchmark; NOT independently held-out",
            "questions": [{"id": c["id"], "question": c["question"],
                           "kind": c["kind"], "expectedPathId": c["expected_path_id"],
                           "source": c["source"], "domain": c["domain"]}
                          for c in cases]}


def run_case(case_id, index_sha256, execute=False, pilot=False, *, question_override=None):
    if not isinstance(case_id, str) or not isinstance(index_sha256, str) or type(execute) is not bool:
        raise ValueError("caseId, indexSha256 and boolean execute are required")
    compiler, planner, benchmark, index, docs, cases, digest = _catalog()
    if index_sha256 != digest:
        raise ValueError("Ontology catalog changed; refresh the benchmark question list")
    case = next((c for c in (PILOT_CASES if pilot else cases) if c["id"] == case_id), None)
    if case is None:
        raise ValueError("Unknown frozen benchmark case")
    if question_override is not None:
        if not pilot or not isinstance(question_override, str) or not question_override.strip() or len(question_override) > 1000:
            raise ValueError("Question override is restricted to nonempty Experiment 42 local tests")
        case = {**case, "question": question_override}
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("Another benchmark case is running")
    try:
        exp30 = _load("ui37_retrieval", "experiments/vector_graph_rag/30_evaluate_simple_questions.py")
        exp33 = _load("ui37_llm", "experiments/vector_graph_rag/33_llm_sparql.py")
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        embedding_model = os.environ.get("TEP_BENCHMARK_EMBEDDING_MODEL", "nomic-embed-text:latest")
        model = os.environ.get("TEP_QUERY_MODEL", "llama3.1:8b")
        timeout = 180
        top_k = 8
        key = (digest, embedding_model, ollama_url)
        if key not in _CACHE:
            cache_path = HERE / "data/ontology_multihop_36_embedding_cache.json"
            cached = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
            texts = [d["text"] for d in docs]
            uris = [d["uri"] for d in docs]
            if (cached.get("index_sha256") == digest and cached.get("model") == embedding_model
                    and cached.get("uris") == uris and cached.get("texts") == texts):
                vectors = cached["vectors"]
            else:
                vectors = exp30.embed(ollama_url, embedding_model, texts, timeout)
            _CACHE.clear()
            _CACHE[key] = vectors
        started = time.monotonic()
        lex = exp30.lexical_ranking(case["question"], docs)
        vec = exp30.vector_ranking(exp30.embed(ollama_url, embedding_model, [case["question"]], timeout)[0], _CACHE[key], docs)
        ranked = exp30.fusion(lex, vec, docs, 0.75)
        candidates = [docs[i] for i in ranked[:top_k]]
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
        raw = exp33.ollama(ollama_url, model, prompt, timeout)
        chosen = planner.parse_choice(raw, {d["uri"] for d in candidates})
        result = {"experiment": 42 if pilot else 37, "caseId": case_id, "question": case["question"],
                  "expectedPathId": case["expected_path_id"], "selectedPathId": chosen,
                  "correctPathSelection": (chosen == case["expected_path_id"]) if case["expected_path_id"] else None,
                  "indexSha256": digest, "model": model, "embeddingModel": embedding_model,
                  "candidatePaths": [{"pathId": d["uri"], "domain": d["domain"],
                                      "predicates": d["path"]["predicates"]} for d in candidates],
                  "llmRaw": raw, "validation": "Valid catalog path selection or ABSTAIN",
                  "execution": "not_requested", "answerStatus": "NOT_VERIFIED", "pilot": pilot}
        if chosen == "ABSTAIN":
            result["execution"] = "not_applicable"
            result["answer"] = "ABSTAIN — no supported path selected."
        else:
            doc = next(d for d in candidates if d["uri"] == chosen)
            compiled = compiler.compile_plan(
                {"operation": "nested_path_select", "predicates": doc["path"]["predicates"], "limit": 10}, index)
            result["query"] = compiled["query"]
            result["pathEvidence"] = compiled.get("path_evidence")
            result["answer"] = "Validated SPARQL path compiled. No natural-language answer verification performed."
            if execute:
                exp32 = _load("ui37_execute", "experiments/vector_graph_rag/32_execute_simple_sparql.py")
                try:
                    bindings = exp32.execute(os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"), compiled["query"], timeout)
                    result.update({"execution": "ok", "returnedRows": len(bindings),
                                   "sampleBindings": bindings[:10],
                                   "answer": "GraphDB returned " + str(len(bindings)) + " row(s). See bindings; correctness not verified."})
                except Exception as exc:
                    result.update({"execution": "error", "executionError": str(exc)})
        result["elapsedSeconds"] = round(time.monotonic() - started, 2)
        return result
    finally:
        _LOCK.release()


# Frozen pilot wording. These are development probes, NOT gold-answer annotations.
# The path-only 36D planner cannot solve every question below.
PILOT_CASES = [
    {"id": "E42-01", "question": "Which equipment items are defined in the DEXPI engineering model?", "kind": "entity", "domain": "dexpi"},
    {"id": "E42-02", "question": "Which instruments are associated with reactor equipment in the engineering model?", "kind": "relationship", "domain": "dexpi"},
    {"id": "E42-03", "question": "Which components belong to equipment assemblies through nested DEXPI equipment relationships?", "kind": "multihop", "domain": "dexpi"},
    {"id": "E42-04", "question": "Which engineering assets have an explicitly evidenced connection to an ECAD device?", "kind": "cross_domain", "domain": None},
    {"id": "E42-05", "question": "Which vessels have a design-pressure value above 10 bar?", "kind": "filter", "domain": None},
    {"id": "E42-06", "question": "Which DEXPI equipment resources can be traced to their containing equipment collection?", "kind": "reverse_relationship", "domain": "dexpi"},
    {"id": "E42-07", "question": "Which ECAD devices are verified as physically installed on the reactor, rather than merely proposed candidates?", "kind": "evidence", "domain": None},
    {"id": "E42-08", "question": "Which equipment items have a verified connection to an asset inventory record and an ECAD device?", "kind": "multi_constraint", "domain": None},
]
for _case in PILOT_CASES:
    _case.update({"expected_path_id": None, "source": "authored engineering pilot; gold annotation pending"})

def pilot_questions():
    _, _, _, _, _, _, digest = _catalog()
    return {"experiment": 42, "indexSha256": digest,
            "provenance": "Eight frozen authored development probes; gold answers NOT yet verified",
            "questions": [{"id": c["id"], "question": c["question"], "kind": c["kind"],
                           "expectedPathId": None, "source": c["source"], "domain": c["domain"]}
                          for c in PILOT_CASES]}
