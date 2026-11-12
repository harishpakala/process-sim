"""Experiment 28: LLM-assisted selection from frozen ontology retrieval.

Requires: pip install openai
Set OPENAI_API_KEY in your shell. No API calls are made with --dry-run.
The model never sees gold labels or domain labels, and can only return
candidate IDs; URI and domain resolution remain deterministic.
"""
import argparse
import hashlib
import json
import os
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).parent


def load_module(name, filename):
    spec = spec_from_file_location(name, ROOT / filename)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def candidate_set(hits, k, index_uris):
    unique = []
    seen = set()
    for rank, hit in enumerate(hits[:k], 1):
        uri = hit.get("uri")
        if not uri or uri not in index_uris or uri in seen:
            continue
        seen.add(uri)
        unique.append({"id": len(unique) + 1, "rank": rank, "uri": uri})
    return unique


def select(client, model, question, candidates, index_by_uri):
    options = []
    for c in candidates:
        info = index_by_uri[c["uri"]]
        options.append({
            "candidate_id": c["id"],
            "concept_name": c["uri"].rsplit("/", 1)[-1].rsplit("#", 1)[-1],
            "kind": info.get("kind"),
            "label": info.get("label"),
            "description": info.get("description"),
        })
    prompt = {
        "question": question,
        "candidate_concepts": options,
        "task": "Select the minimal set of concepts necessary to answer the question. "
                "Do not choose related-but-unnecessary concepts. "
                "Identifiers used to match entities can be selected, but not as domain evidence. "
                "If no candidates suffice, return empty lists. "
                "Do not infer domains from namespaces; select by concept semantics.",
    }
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "selected_candidate_ids": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["selected_candidate_ids"],
    }
    start = time.perf_counter()
    response = client.responses.create(
        model=model,
        instructions="You are an ontology concept relevance selector. Return JSON matching the schema. "
                     "Only select candidate IDs provided. Never invent an ID.",
        input=json.dumps(prompt, ensure_ascii=False),
        text={"format": {"type": "json_schema", "name": "dtwise_concept_selection",
                         "strict": True, "schema": schema}},
    )
    elapsed = time.perf_counter() - start
    if not response.output_text:
        raise ValueError("Model returned no usable output (possibly refusal or incomplete response)")
    parsed = json.loads(response.output_text)
    ids = parsed["selected_candidate_ids"]
    valid = {c["id"] for c in candidates}
    if len(ids) != len(set(ids)) or any(type(i) is not int or i not in valid for i in ids):
        raise ValueError(f"Invalid candidate IDs from model: {ids!r}")
    usage = response.usage
    return ids, elapsed, {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def concept_metrics(gold, predicted):
    g, p = set(gold), set(predicted)
    matched = len(g & p)
    return {
        "required": len(g), "selected": len(p), "matched": matched,
        "precision": matched / len(p) if p else (1.0 if not g else 0.0),
        "recall": matched / len(g) if g else 1.0,
        "complete_coverage": g <= p,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--reviewed", type=Path, default=ROOT / "data/reviewed_concepts_6.json")
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/llm_concept_selection_28.json")
    ap.add_argument("--mode", choices=["lexical", "vector", "hybrid"], default="hybrid")
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Process only first N questions (0 = all)")
    a = ap.parse_args()
    if a.top_k < 1 or a.limit < 0:
        ap.error("top-k must be positive and limit nonnegative")
    policy = load_module("concept_role_policy", "concept_role_policy.py")
    exp25 = load_module("exp25", "25_evaluate_ontology_resolved_domains.py")
    index, benchmark, reviewed, retrieval = map(read, (a.index, a.benchmark, a.reviewed, a.retrieval))
    index_by_uri = {c["uri"]: c for c in index["concepts"] if c.get("uri")}
    mapping = exp25.resolver(index)
    by_id = {r["id"]: r for r in retrieval["results"]}
    cases = {c["id"]: c for c in benchmark["cases"]}
    annotated = reviewed["cases"]
    if len(by_id) != len(retrieval["results"]) or len(cases) != len(benchmark["cases"]):
        raise ValueError("Duplicate IDs in input data")
    if any(c["id"] not in cases or c["id"] not in by_id for c in annotated):
        raise ValueError("Reviewed case missing from benchmark or retrieval")
    if a.limit:
        annotated = annotated[:a.limit]
    if not a.dry_run:
        if not os.environ.get("OPENAI_API_KEY"):
            ap.error("OPENAI_API_KEY is missing; set it or use --dry-run")
        try:
            from openai import OpenAI
        except ImportError:
            ap.error("Install the OpenAI SDK: python -m pip install openai")
        client = OpenAI(timeout=90.0, max_retries=1)
    else:
        client = None
    results = []
    for case in annotated:
        qid = case["id"]
        hits = by_id[qid][a.mode]["hits"]
        candidates = candidate_set(hits, a.top_k, index_by_uri)
        gold = [c["uri"] for c in case["required"]]
        if any(uri not in index_by_uri for uri in gold):
            raise ValueError(f"Gold concept URI not found in ontology: {qid}")
        baseline = [c["uri"] for c in candidates]
        baseline_metrics = concept_metrics(gold, baseline)
        row = {"id": qid, "question": cases[qid]["question"],
               "candidates": candidates,
               "baseline_topk": baseline_metrics,
               "candidate_ceiling": {"all_required_retrieved": baseline_metrics["complete_coverage"]}}
        if a.dry_run:
            print(f"{qid}: {len(candidates)} unique candidates, "
                  f"required in top-{a.top_k}: {baseline_metrics['matched']}/{len(gold)}")
        else:
            ids, seconds, usage = select(client, a.model, cases[qid]["question"],
                                         candidates, index_by_uri)
            selected = [c["uri"] for c in candidates if c["id"] in ids]
            domain_concepts = [uri for uri in selected if policy.eligible_for_domain_evidence(uri)]
            linking = [uri for uri in selected if not policy.eligible_for_domain_evidence(uri)]
            domains = sorted({next(iter(mapping[uri])) for uri in domain_concepts
                              if len(mapping.get(uri, ())) == 1})
            row["llm"] = {
                "selected_uris": selected,
                "domain_evidence_uris": domain_concepts,
                "graph_linking_uris": linking,
                "predicted_domains": domains,
                "concept_metrics": concept_metrics(gold, selected),
                "domain_metrics": exp25.metrics(cases[qid]["expected_domains"], domains),
                "latency_seconds": round(seconds, 3),
                "usage": usage,
            }
            print(f"{qid}: concept recall {row['llm']['concept_metrics']['recall']:.3f}, "
                  f"precision {row['llm']['concept_metrics']['precision']:.3f}, "
                  f"domains={domains}, latency={seconds:.1f}s")
        results.append(row)
        # Save after each completed case for partial recovery; no overwriting on failure.
        report = {
            "experiment": "28_llm_concept_selection",
            "dry_run": a.dry_run, "model": None if a.dry_run else a.model,
            "mode": a.mode, "top_k": a.top_k,
            "reviewed_case_count": len(annotated),
            "completed": len(results),
            "results": results,
            "input_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in (("index", a.index), ("benchmark", a.benchmark),
                                                ("reviewed", a.reviewed), ("retrieval", a.retrieval))},
            "limitations": [
                "Only six reviewed cases exist; no untouched test set.",
                "Gold required concepts used for evaluation only; never sent to the LLM.",
                "Frozen retrieval results may use hybrid fusion weight 0.70, not 0.75; check provenance.",
                "Candidate ceiling limits possible recall; no ontology concept generation.",
                "Graph-linking concepts are retained but traversal is not executed.",
                "Cost depends on model pricing; token counts and latency are recorded.",
            ],
        }
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not a.dry_run and results:
        for label, key in (("top-k baseline", "baseline_topk"), ("LLM selector", "llm")):
            scores = [r[key] if key == "baseline_topk" else r[key]["concept_metrics"] for r in results]
            print(f"{label}: mean precision={sum(s['precision'] for s in scores)/len(scores):.3f}, "
                  f"mean recall={sum(s['recall'] for s in scores)/len(scores):.3f}, "
                  f"complete={sum(s['complete_coverage'] for s in scores)}/{len(scores)}")
    print("Saved:", a.output)


if __name__ == "__main__":
    main()
