"""Experiment 26: ablate exact AssetIdentifier ontology concepts as domain evidence.

Preserves all retrieval hits and ontology mappings. Only domain voting changes.
The URI set is discovered from the index by exact local name AssetIdentifier;
no substring matches (e.g. hasAssetIdentifier) and no gold-label leakage.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).parent
MODES = ("lexical", "vector", "hybrid")


def load25():
    spec = spec_from_file_location("exp25", ROOT / "25_evaluate_ontology_resolved_domains.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_name(uri):
    p = urlsplit(uri)
    return unquote(p.fragment or p.path.rstrip("/").rsplit("/", 1)[-1])


def excluded_uris(index):
    result = {}
    for c in index["concepts"]:
        uri = c.get("uri")
        if c.get("kind") in ("class", "property") and uri and local_name(uri).casefold() == "assetidentifier":
            result.setdefault(uri, set()).add(c.get("domain"))
    return {uri: sorted(ds) for uri, ds in sorted(result.items())}


def baseline_vote(hits, excluded=frozenset(), threshold=0.65, max_domains=3):
    # Frozen baseline formula: keep original ranks, even after exclusions.
    scores = {}
    for rank, hit in enumerate(hits, 1):
        if hit.get("uri") in excluded:
            continue
        domain = hit.get("domain")
        if domain:
            scores[domain] = scores.get(domain, 0) + 1 / (rank + 5)
    if not scores:
        return []
    order = sorted(scores, key=lambda d: (-scores[d], d))
    return [d for d in order if scores[d] >= threshold * scores[order[0]]][:max_domains]


def union_vote(hits, mapping, excluded=frozenset(), k=10):
    domains = set()
    seen = set()
    for hit in hits[:k]:
        uri = hit.get("uri")
        if not uri or uri in seen or uri in excluded:
            continue
        seen.add(uri)
        associated = mapping.get(uri, ())
        if len(associated) == 1:
            domains.update(associated)
    return sorted(domains)


def summarize(rows):
    n = len(rows)
    return {
        "evaluated": n,
        "exact_accuracy": sum(r["metrics"]["exact"] for r in rows) / n,
        "macro_f1": sum(r["metrics"]["f1"] for r in rows) / n,
        "macro_precision": sum(r["metrics"]["precision"] for r in rows) / n,
        "macro_recall": sum(r["metrics"]["recall"] for r in rows) / n,
        "false_positives": sum(len(r["metrics"]["false_positive"]) for r in rows),
        "missed": sum(len(r["metrics"]["missed"]) for r in rows),
    }


def evaluate(index, benchmark, retrieval, k=10):
    e25 = load25()
    mapping = e25.resolver(index)
    excluded = excluded_uris(index)
    ids = set(excluded)
    cases = benchmark["cases"]
    results = retrieval["results"]
    by_id = {r["id"]: r for r in results}
    if len(by_id) != len(results) or len({c["id"] for c in cases}) != len(cases) or set(by_id) != {c["id"] for c in cases}:
        raise ValueError("Benchmark/retrieval IDs missing or duplicated")
    params = retrieval.get("parameters", {})
    if params.get("domain_threshold") != 0.65 or params.get("max_domains") != 3:
        raise ValueError("Frozen baseline must use domain_threshold=0.65 and max_domains=3")
    methods = ("frozen_baseline", "baseline_without_assetidentifier",
               "top10_unique_union", "top10_unique_union_without_assetidentifier")
    output = {}
    occurrences = []
    for mode in MODES:
        rows = {m: [] for m in methods}
        for case in cases:
            qid = case["id"]
            record = by_id[qid][mode]
            hits = record["hits"]
            frozen = record["selected_domains"]
            if baseline_vote(hits) != frozen:
                raise ValueError(f"Frozen baseline does not reproduce: {mode} {qid}")
            choices = (
                frozen,
                baseline_vote(hits, ids),
                union_vote(hits, mapping, k=k),
                union_vote(hits, mapping, ids, k),
            )
            for rank, hit in enumerate(hits, 1):
                if hit.get("uri") in ids:
                    occurrences.append({"mode": mode, "id": qid, "rank": rank,
                                        "uri": hit["uri"], "domain": hit.get("domain"),
                                        "in_top_k": rank <= k})
            for method, pred in zip(methods, choices):
                rows[method].append({"id": qid, "predicted_domains": pred,
                                     "metrics": e25.metrics(case["expected_domains"], pred)})
        output[mode] = {m: {"summary": summarize(r), "cases": r} for m, r in rows.items()}
    changes = {}
    for mode in MODES:
        changes[mode] = {}
        for before, after in (("frozen_baseline", "baseline_without_assetidentifier"),
                              ("top10_unique_union", "top10_unique_union_without_assetidentifier")):
            a = output[mode][before]
            b = output[mode][after]
            changes[mode][after] = {
                "changed_questions": [
                    {"id": x["id"], "before": x["predicted_domains"], "after": y["predicted_domains"],
                     "before_false_positive": x["metrics"]["false_positive"],
                     "after_false_positive": y["metrics"]["false_positive"],
                     "before_missed": x["metrics"]["missed"], "after_missed": y["metrics"]["missed"]}
                    for x, y in zip(a["cases"], b["cases"])
                    if x["predicted_domains"] != y["predicted_domains"]
                ],
                "delta_false_positives": b["summary"]["false_positives"] - a["summary"]["false_positives"],
                "delta_missed": b["summary"]["missed"] - a["summary"]["missed"],
                "delta_macro_f1": b["summary"]["macro_f1"] - a["summary"]["macro_f1"],
            }
    return {
        "experiment": "assetidentifier_domain_evidence_ablation_15",
        "top_k": k, "excluded_exact_local_name": "AssetIdentifier",
        "excluded_uris": excluded, "excluded_hit_occurrences": occurrences,
        "methods": {
            "frozen_baseline": "Stored original rank-weighted domain selection",
            "baseline_without_assetidentifier": "Same rank-weighted rule, omitting only exact excluded URIs; original ranks retained",
            "top10_unique_union": "Top-k unique URI union of uniquely associated ontology domains",
            "top10_unique_union_without_assetidentifier": "Same union with exact excluded URIs omitted from voting",
        },
        "results": output, "paired_changes": changes,
        "limitations": [
            "Only exact local name AssetIdentifier is excluded; no substring or semantic matching.",
            "Index may contain zero matching concepts; a zero-effect result is then expected.",
            "Exclusion affects domain voting only, not retrieval, ontology resolution or graph traversal.",
            "15 previously inspected questions with provisional expected domains; descriptive ablation only.",
            "No claim of causal improvement beyond this frozen dataset.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--benchmark", type=Path, default=ROOT / "data/benchmark_15.json")
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/assetidentifier_ablation_15.json")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args()
    if a.top_k < 1:
        ap.error("--top-k must be positive")
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    report = evaluate(load(a.index), load(a.benchmark), load(a.retrieval), a.top_k)
    report["input_sha256"] = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in
                              (("index", a.index), ("benchmark", a.benchmark), ("retrieval", a.retrieval))}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Exact AssetIdentifier URIs:", len(report["excluded_uris"]))
    for uri, ds in report["excluded_uris"].items():
        print(" ", uri, "=>", ", ".join(ds))
    print("Matching retrieved hits:", len(report["excluded_hit_occurrences"]))
    print("mode     method                                     exact  macro-F1  precision recall  false+ missed")
    for mode, methods in report["results"].items():
        for name, data in methods.items():
            s = data["summary"]
            print(f"{mode:<8} {name:<42} {s['exact_accuracy']:.3f}  {s['macro_f1']:.3f}     "
                  f"{s['macro_precision']:.3f}     {s['macro_recall']:.3f}   "
                  f"{s['false_positives']:>3}    {s['missed']:>3}")
    print("Paired differences:")
    for mode, changes in report["paired_changes"].items():
        for method, d in changes.items():
            print(f"  {mode} {method}: changed={len(d['changed_questions'])} "
                  f"delta_false+={d['delta_false_positives']:+d} delta_missed={d['delta_missed']:+d} "
                  f"delta_F1={d['delta_macro_f1']:+.3f}")
            for row in d["changed_questions"]:
                print(f"    {row['id']}: {row['before']} -> {row['after']}")
    print("Wrote:", a.output)


if __name__ == "__main__":
    main()
