"""Compare frozen concept-to-domain inference rules on the 15-question benchmark.

No expected domain labels are used for inference or cardinality selection.
All rules are predefined; results are descriptive, not held-out validation.
"""
import argparse
import hashlib
import json
from pathlib import Path

MODES = ("lexical", "vector", "hybrid")
ROOT = Path(__file__).parent


def baseline_select(hits, max_domains=3, threshold=0.65):
    scores = {}
    for rank, hit in enumerate(hits, 1):
        d = hit.get("domain")
        if d:
            scores[d] = scores.get(d, 0) + 1 / (rank + 5)
    if not scores:
        return []
    order = sorted(scores, key=lambda d: (-scores[d], d))
    return [d for d in order if scores[d] >= threshold * scores[order[0]]][:max_domains]


def concept_first(hits, k=10, threshold=0.65, max_domains=3, confidence=False):
    # Count each domain+URI once; do not count repeated pseudo-concepts.
    evidence = {}
    seen = set()
    for rank, hit in enumerate(hits[:k], 1):
        d, uri = hit.get("domain"), hit.get("uri")
        if not d or not uri or hit.get("kind") not in ("class", "property"):
            continue
        key = (d, uri)
        if key in seen:
            continue
        seen.add(key)
        item = evidence.setdefault(d, {"score": 0.0, "count": 0, "best_rank": rank})
        item["score"] += 1 / (rank + 5)
        item["count"] += 1
        item["best_rank"] = min(item["best_rank"], rank)
    if not evidence:
        return [], evidence
    order = sorted(evidence, key=lambda d: (-evidence[d]["score"], d))
    best = evidence[order[0]]["score"]
    selected = []
    for d in order:
        e = evidence[d]
        if e["score"] < threshold * best:
            continue
        # Fixed confidence gate: two distinct concepts OR a top-three hit.
        if confidence and not (e["count"] >= 2 or e["best_rank"] <= 3):
            continue
        selected.append(d)
        if len(selected) == max_domains:
            break
    return selected, evidence


def metrics(expected, predicted):
    gold, pred = set(expected), set(predicted)
    tp = len(gold & pred)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"exact": int(gold == pred), "precision": precision, "recall": recall,
            "f1": f1, "false_positive_domains": sorted(pred - gold),
            "missed_domains": sorted(gold - pred)}


def summarize(rows):
    n = len(rows)
    return {
        "evaluated": n,
        "exact_domain_set_accuracy": sum(r["metrics"]["exact"] for r in rows) / n if n else None,
        "macro_domain_precision": sum(r["metrics"]["precision"] for r in rows) / n if n else None,
        "macro_domain_recall": sum(r["metrics"]["recall"] for r in rows) / n if n else None,
        "macro_domain_f1": sum(r["metrics"]["f1"] for r in rows) / n if n else None,
        "mean_predicted_domain_count": sum(len(r["predicted_domains"]) for r in rows) / n if n else None,
        "total_false_positive_domains": sum(len(r["metrics"]["false_positive_domains"]) for r in rows),
        "total_missed_domains": sum(len(r["metrics"]["missed_domains"]) for r in rows),
    }


def evaluate(benchmark, retrieval, k=10, threshold=0.65, max_domains=3, verify_baseline=True):
    cases = benchmark["cases"]
    results = retrieval["results"]
    by_id = {r["id"]: r for r in results}
    if len(by_id) != len(results) or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate question IDs")
    if set(by_id) != {c["id"] for c in cases}:
        raise ValueError("Retrieval IDs must exactly match benchmark IDs")
    params = retrieval.get("parameters", {})
    if verify_baseline and (params.get("domain_threshold") != 0.65 or
                            params.get("max_domains") != 3):
        raise ValueError("Expected frozen baseline threshold=0.65, max_domains=3")
    methods = ("original_baseline", "concept_first_top10", "concept_first_confidence")
    output = {}
    for mode in MODES:
        rows_by_method = {method: [] for method in methods}
        for case in cases:
            result = by_id[case["id"]]
            hits = result[mode]["hits"]
            if len(hits) < k:
                # Lexical results may contain fewer than k positive-score hits.
                pass
            original = result[mode].get("selected_domains")
            if original is None:
                raise ValueError(f"Missing frozen selected_domains: {case['id']} {mode}")
            if verify_baseline and original != baseline_select(hits, 3, 0.65):
                raise ValueError(f"Frozen baseline does not reproduce: {case['id']} {mode}")
            b, evidence = concept_first(hits, k, threshold, max_domains)
            c, _ = concept_first(hits, k, threshold, max_domains, confidence=True)
            for method, predicted in zip(methods, (original, b, c)):
                rows_by_method[method].append({
                    "id": case["id"], "predicted_domains": predicted,
                    "metrics": metrics(case["expected_domains"], predicted),
                    "domain_evidence": evidence if method != "original_baseline" else None,
                })
        output[mode] = {method: {"summary": summarize(rows), "cases": rows}
                        for method, rows in rows_by_method.items()}
    return {
        "experiment": "concept_to_domain_inference_15",
        "status": "descriptive_predefined_rules_on_provisional_domain_labels",
        "parameters": {"concept_top_k": k, "relative_threshold": threshold,
                       "max_domains": max_domains, "baseline_threshold": 0.65,
                       "baseline_max_domains": 3},
        "methods": {
            "original_baseline": "Stored original selected_domains, verified against script 19's rank/(rank+5) aggregation on all available hits",
            "concept_first_top10": "Top-k unique class/property URI hits; rank/(rank+5) evidence; relative threshold",
            "concept_first_confidence": "Same as concept_first_top10, plus >=2 unique concepts or best hit at rank <=3",
        },
        "results": output,
        "limitations": [
            "Expected domains are provisional; confirm ontology domain labels before publication.",
            "Same 15 questions were previously inspected; not an untouched holdout.",
            "Rule comparisons are descriptive and do not establish an optimized domain selector.",
            "Gold expected_domains are used only for scoring, never for inference.",
            "No instance correspondence, joins, or historical observations are validated.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/concept_to_domain_eval_15.json")
    args = ap.parse_args()
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    result = evaluate(load(args.benchmark), load(args.retrieval))
    result["input_sha256"] = {
        "benchmark": hashlib.sha256(args.benchmark.read_bytes()).hexdigest(),
        "retrieval": hashlib.sha256(args.retrieval.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("mode     method                     exact    macro-F1  precision recall  false+  missed")
    for mode, methods in result["results"].items():
        for name, data in methods.items():
            s = data["summary"]
            print(f"{mode:<8} {name:<26} {s['exact_domain_set_accuracy']:.3f}    "
                  f"{s['macro_domain_f1']:.3f}     {s['macro_domain_precision']:.3f}     "
                  f"{s['macro_domain_recall']:.3f}   {s['total_false_positive_domains']:>3}     "
                  f"{s['total_missed_domains']:>3}")
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
