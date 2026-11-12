"""Experiment 27: fixed DTWiSE concept-role policy, preserving graph-linking hits.

Reports paired baseline vs role-aware predictions and records the original
hasAssetIdentifier hits for future graph traversal. No gold used in inference.
"""
import argparse
import hashlib
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).parent


def import_local(name, filename):
    spec = spec_from_file_location(name, ROOT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(index, benchmark, retrieval, k):
    ablation = import_local("exp26", "26_ablate_assetidentifier_domain_evidence.py")
    policy = import_local("concept_role_policy", "concept_role_policy.py")
    exp25 = import_local("exp25", "25_evaluate_ontology_resolved_domains.py")
    mapping = exp25.resolver(index)
    expected_uris = {
        uri for uri in mapping if policy.concept_role(uri) == "graph_linking"
    }
    if not expected_uris:
        raise ValueError("Policy matches no indexed concept URIs")
    # Ensure the policy matches only the intended exact URI local name.
    if any(policy.local_name(uri) != "hasAssetIdentifier" for uri in expected_uris):
        raise ValueError("Unexpected policy exclusion")
    by_id = {r["id"]: r for r in retrieval["results"]}
    cases = benchmark["cases"]
    if len(by_id) != len(retrieval["results"]) or len({c["id"] for c in cases}) != len(cases) or set(by_id) != {c["id"] for c in cases}:
        raise ValueError("Duplicate or mismatched question IDs")
    params = retrieval.get("parameters", {})
    if params.get("domain_threshold") != 0.65 or params.get("max_domains") != 3:
        raise ValueError("Frozen baseline parameters differ")
    modes = ("lexical", "vector", "hybrid")
    methods = ("frozen_baseline", "role_aware_rank_weighted",
               "topk_unique_union", "role_aware_topk_unique_union")
    output = {}
    for mode in modes:
        rows = {m: [] for m in methods}
        for case in cases:
            qid = case["id"]
            record = by_id[qid][mode]
            hits = record["hits"]
            original = record["selected_domains"]
            if ablation.baseline_vote(hits) != original:
                raise ValueError(f"Frozen baseline mismatch: {mode} {qid}")
            choices = [
                original,
                ablation.baseline_vote(hits, expected_uris),
                ablation.union_vote(hits, mapping, k=k),
                ablation.union_vote(hits, mapping, expected_uris, k),
            ]
            parts = policy.partition_retrieved_hits(hits)
            graph_hits = [
                {"rank": x["rank"], "uri": x["hit"].get("uri"),
                 "domain_associations": sorted(mapping.get(x["hit"].get("uri"), ())),
                 "retrieval_domain": x["hit"].get("domain"),
                 "kind": x["hit"].get("kind")}
                for x in parts["graph_linking"]
            ]
            for method, predicted in zip(methods, choices):
                rows[method].append({
                    "id": qid, "predicted_domains": predicted,
                    "metrics": exp25.metrics(case["expected_domains"], predicted),
                    "graph_linking_hits_retained": graph_hits if method.startswith("role_aware") else None,
                })
        output[mode] = {m: {"summary": ablation.summarize(r), "cases": r} for m, r in rows.items()}
    deltas = {}
    for mode in modes:
        deltas[mode] = {}
        for before, after in (("frozen_baseline", "role_aware_rank_weighted"),
                              ("topk_unique_union", "role_aware_topk_unique_union")):
            a = output[mode][before]
            b = output[mode][after]
            deltas[mode][after] = {
                "delta_false_positives": b["summary"]["false_positives"] - a["summary"]["false_positives"],
                "delta_missed": b["summary"]["missed"] - a["summary"]["missed"],
                "delta_macro_f1": b["summary"]["macro_f1"] - a["summary"]["macro_f1"],
                "changed_questions": [
                    {"id": x["id"], "before": x["predicted_domains"], "after": y["predicted_domains"]}
                    for x, y in zip(a["cases"], b["cases"]) if x["predicted_domains"] != y["predicted_domains"]
                ],
            }
    return {
        "experiment": "fixed_concept_role_policy_15",
        "policy": {"graph_linking_only_local_names": ["hasAssetIdentifier"],
                   "matched_uris": sorted(expected_uris),
                   "domain_evidence": "excluded",
                   "retrieval": "preserved", "ontology_resolution": "preserved",
                   "graph_planning": "hits retained for future implementation"},
        "top_k": k, "results": output, "paired_deltas": deltas,
        "limitations": [
            "Role policy is a design choice, not evidence of superior accuracy.",
            "Graph-linking hits are retained in the report; graph execution is not implemented.",
            "Gold domains are used for scoring only, never for domain selection.",
            "Previously inspected 15 questions and provisional expected domains.",
            "No semantic normalization beyond exact hasAssetIdentifier URI local name.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/concept_role_policy_eval_15.json")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args()
    if a.top_k < 1:
        ap.error("--top-k must be positive")
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    report = evaluate(load(a.index), load(a.benchmark), load(a.retrieval), a.top_k)
    report["input_sha256"] = {n: hashlib.sha256(p.read_bytes()).hexdigest()
                              for n, p in (("index", a.index), ("benchmark", a.benchmark),
                                           ("retrieval", a.retrieval))}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Graph-linking-only URIs:", len(report["policy"]["matched_uris"]))
    for uri in report["policy"]["matched_uris"]:
        print(" ", uri)
    print("mode     method                         exact  macro-F1  precision  recall  false+  missed")
    for mode, methods in report["results"].items():
        for name, result in methods.items():
            s = result["summary"]
            print(f"{mode:<8} {name:<30} {s['exact_accuracy']:.3f}  "
                  f"{s['macro_f1']:.3f}     {s['macro_precision']:.3f}      "
                  f"{s['macro_recall']:.3f}   {s['false_positives']:>3}     {s['missed']:>3}")
    for mode, methods in report["paired_deltas"].items():
        for name, change in methods.items():
            print(f"{mode} {name}: changed={len(change['changed_questions'])}, "
                  f"delta false+={change['delta_false_positives']:+d}, "
                  f"delta missed={change['delta_missed']:+d}, "
                  f"delta F1={change['delta_macro_f1']:+.3f}")
    print("Wrote:", a.output)


if __name__ == "__main__":
    main()
