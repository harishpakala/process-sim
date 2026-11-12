"""Experiment 25: deterministic ontology URI-to-domain resolution and diagnostic selection.

Unique domain in the unified index means unique *indexed association*, not
necessarily vocabulary ownership. Shared concepts do not vote in unique-only
selection. Gold domains are used exclusively for post-hoc scoring.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
MODES = ("lexical", "vector", "hybrid")


def resolver(index):
    mapping = defaultdict(set)
    for c in index["concepts"]:
        if c.get("kind") in ("class", "property"):
            if not c.get("uri") or not c.get("domain"):
                raise ValueError("Class/property missing URI or domain")
            mapping[c["uri"]].add(c["domain"])
    return mapping


def resolve(uri, mapping):
    ds = sorted(mapping.get(uri, ()))
    return {"uri": uri, "status": "unknown" if not ds else
            ("unique_association" if len(ds) == 1 else "shared"),
            "usage_domains": ds}


def metrics(gold, predicted):
    g, p = set(gold), set(predicted)
    precision = len(g & p) / len(p) if p else 0
    recall = len(g & p) / len(g) if g else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"exact": int(g == p), "precision": precision, "recall": recall,
            "f1": f1, "missed": sorted(g - p), "false_positive": sorted(p - g)}


def select(hits, mapping, k, unique_only):
    selected = set()
    seen = set()
    evidence = []
    for rank, hit in enumerate(hits[:k], 1):
        uri = hit.get("uri")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        item = resolve(uri, mapping)
        evidence.append({"rank": rank, **item,
                         "stored_domain": hit.get("domain")})
        if item["status"] == "unique_association" or (
                not unique_only and item["status"] == "shared"):
            selected.update(item["usage_domains"])
    return sorted(selected), evidence


def first_evidence(hits, mapping, domain):
    found = []
    seen = set()
    for rank, hit in enumerate(hits, 1):
        uri = hit.get("uri")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        info = resolve(uri, mapping)
        if domain in info["usage_domains"]:
            found.append({"rank": rank, "uri": uri, "status": info["status"]})
    return found


def summarize(rows):
    n = len(rows)
    return {"evaluated": n,
            "exact_domain_set_accuracy": sum(r["metrics"]["exact"] for r in rows) / n if n else None,
            "macro_precision": sum(r["metrics"]["precision"] for r in rows) / n if n else None,
            "macro_recall": sum(r["metrics"]["recall"] for r in rows) / n if n else None,
            "macro_f1": sum(r["metrics"]["f1"] for r in rows) / n if n else None,
            "false_positive_domains": sum(len(r["metrics"]["false_positive"]) for r in rows),
            "missed_domains": sum(len(r["metrics"]["missed"]) for r in rows)}


def evaluate(index, benchmark, retrieval, k=10):
    mapping = resolver(index)
    cases = benchmark["cases"]
    records = retrieval["results"]
    if len({c["id"] for c in cases}) != len(cases) or len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate question IDs")
    by_id = {r["id"]: r for r in records}
    if set(by_id) != {c["id"] for c in cases}:
        raise ValueError("Benchmark and retrieval IDs differ")
    methods = ("frozen_baseline", "topk_all_associations", "topk_unique_associations")
    output = {}
    for mode in MODES:
        per_method = {m: [] for m in methods}
        for case in cases:
            qid = case["id"]
            hits = by_id[qid][mode]["hits"]
            frozen = by_id[qid][mode].get("selected_domains")
            if frozen is None:
                raise ValueError(f"Missing frozen baseline selection: {qid} {mode}")
            union, evidence = select(hits, mapping, k, unique_only=False)
            unique, _ = select(hits, mapping, k, unique_only=True)
            for method, predicted in zip(methods, (frozen, union, unique)):
                score = metrics(case["expected_domains"], predicted)
                misses = {}
                for d in score["missed"]:
                    occurrences = first_evidence(hits, mapping, d)
                    misses[d] = {
                        "first_associated_rank": occurrences[0]["rank"] if occurrences else None,
                        "first_unique_association_rank": next(
                            (x["rank"] for x in occurrences if x["status"] == "unique_association"), None),
                        "associated_hits_at_11_to_30": sum(10 < x["rank"] <= 30 for x in occurrences),
                        "associated_hits": occurrences,
                        "diagnostic": ("not_retrieved_in_saved_hits" if not occurrences else
                                       "first_evidence_below_top_k" if occurrences[0]["rank"] > k else
                                       "within_top_k_but_not_selected"),
                    }
                per_method[method].append({
                    "id": qid, "predicted_domains": predicted, "metrics": score,
                    "miss_diagnostics": misses,
                    "top_k_concept_resolution": evidence if method == "topk_unique_associations" else None,
                })
        output[mode] = {m: {"summary": summarize(rows), "cases": rows}
                        for m, rows in per_method.items()}
    shared = {uri: sorted(ds) for uri, ds in mapping.items() if len(ds) > 1}
    return {
        "experiment": "ontology_resolved_domain_selection_15",
        "top_k": k,
        "index_concepts_with_uri": len(mapping),
        "shared_uris": shared,
        "methods": {
            "frozen_baseline": "Stored original selected_domains; unchanged",
            "topk_all_associations": "Union of ontology-index domain associations for unique URIs in top k",
            "topk_unique_associations": "Union only for top-k URIs associated with exactly one indexed engineering domain; shared URIs abstain",
        },
        "results": output,
        "limitations": [
            "The index domain field records an association; uniqueness does not establish vocabulary ownership.",
            "Shared URI associations are not evidence that all associated domains are required.",
            "All-associations union and unique-only union are deterministic but do not solve concept relevance.",
            "Rank diagnostics describe retrieved associations, not human-verified concept relevance.",
            "Gold expected_domains used only for evaluation; provisional labels and previously inspected questions.",
            "No query execution, instance joins, or temporal data validated.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/ontology_resolved_domain_eval_15.json")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args()
    if a.top_k < 1:
        ap.error("--top-k must be positive")
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    report = evaluate(load(a.index), load(a.benchmark), load(a.retrieval), a.top_k)
    report["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for name, path in (("index", a.index), ("benchmark", a.benchmark),
                                                 ("retrieval", a.retrieval))}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Shared ontology URIs:", len(report["shared_uris"]))
    for uri, ds in sorted(report["shared_uris"].items()):
        print("  ", uri, "=>", ", ".join(ds))
    print("mode     method                       exact  macro-F1  precision  recall  false+  missed")
    for mode, methods in report["results"].items():
        for name, data in methods.items():
            s = data["summary"]
            print(f"{mode:<8} {name:<28} {s['exact_domain_set_accuracy']:.3f}  "
                  f"{s['macro_f1']:.3f}     {s['macro_precision']:.3f}      "
                  f"{s['macro_recall']:.3f}   {s['false_positive_domains']:>3}      "
                  f"{s['missed_domains']:>3}")
    print("\nHybrid unique-only domain misses:")
    for row in report["results"]["hybrid"]["topk_unique_associations"]["cases"]:
        for domain, detail in row["miss_diagnostics"].items():
            print(f"  {row['id']} {domain}: first_any={detail['first_associated_rank']} "
                  f"first_unique={detail['first_unique_association_rank']} "
                  f"hits_11_to_30={detail['associated_hits_at_11_to_30']} "
                  f"diagnostic={detail['diagnostic']}")
    print("Wrote:", a.output)


if __name__ == "__main__":
    main()
