"""Evaluate ranked ontology concept retrieval against separately reviewed annotations.

No domain selection, query execution, or instance-level mapping inference.
Only annotated questions are scored; unannotated benchmark cases are not failures.
"""
import argparse
import json
from pathlib import Path

MODES = ("lexical", "vector", "hybrid")


def concepts(entries, label):
    if not isinstance(entries, list):
        raise ValueError(f"{label} must be a list")
    keys = []
    for item in entries:
        if not isinstance(item, dict) or not item.get("domain") or not item.get("uri"):
            raise ValueError(f"{label} requires domain and uri for each concept")
        keys.append((item["domain"], item["uri"]))
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate concept in {label}")
    return set(keys)


def evaluate(annotations, report, index=None):
    cases = annotations["cases"]
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate annotation IDs")
    results = report["results"]
    if len({r["id"] for r in results}) != len(results):
        raise ValueError("Duplicate retrieval result IDs")
    by_id = {r["id"]: r for r in results}
    indexed = None
    if index is not None:
        indexed = {(c["domain"], c["uri"]) for c in index["concepts"]
                   if c.get("kind") in ("class", "property")}
    output = {}
    for mode in MODES:
        rows = []
        for case in cases:
            required = concepts(case["required"], case["id"] + " required")
            supporting = concepts(case.get("supporting", []), case["id"] + " supporting")
            excluded = concepts(case.get("excluded", []), case["id"] + " excluded")
            if not required or required & supporting or required & excluded or supporting & excluded:
                raise ValueError("Required must be nonempty and annotation groups disjoint: " + case["id"])
            if indexed is not None and not (required | supporting | excluded) <= indexed:
                raise ValueError("Annotated concept absent from ontology index: " + case["id"])
            row = by_id.get(case["id"])
            if row is None or mode not in row:
                rows.append({"id": case["id"], "status": "missing"})
                continue
            hits = row[mode].get("hits")
            if not isinstance(hits, list):
                raise ValueError("Expected list of ranked hits: " + case["id"])
            ranked = [(h.get("domain"), h.get("uri")) for h in hits]
            if len(ranked) != len(set(ranked)):
                raise ValueError("Duplicate ranked concept: " + case["id"])
            def at(k):
                return len(required & set(ranked[:k]))
            ranks = {key: ranked.index(key) + 1 for key in required if key in ranked}
            first = min(ranks.values()) if ranks else None
            rows.append({
                "id": case["id"], "status": "scored",
                "required_count": len(required),
                "required_found_at_5": at(5),
                "required_found_at_10": at(10),
                "required_recall_at_5": at(5) / len(required),
                "required_recall_at_10": at(10) / len(required),
                "complete_required_coverage_at_10": int(at(10) == len(required)),
                "required_precision_at_10": at(10) / 10,
                "reciprocal_rank_first_required": 1 / first if first else 0.0,
                "first_required_rank": first,
                "supporting_found_at_10": len(supporting & set(ranked[:10])),
                "required_ranks": [
                    {"domain": d, "uri": u, "rank": ranks.get((d, u))}
                    for d, u in sorted(required)
                ],
            })
        scored = [r for r in rows if r["status"] == "scored"]
        def avg(key):
            return sum(r[key] for r in scored) / len(scored) if scored else None
        output[mode] = {"summary": {
            "annotated": len(cases), "evaluated": len(scored),
            "missing": len(cases) - len(scored),
            "mean_required_recall_at_5": avg("required_recall_at_5"),
            "mean_required_recall_at_10": avg("required_recall_at_10"),
            "complete_required_coverage_at_10": avg("complete_required_coverage_at_10"),
            "mean_required_precision_at_10": avg("required_precision_at_10"),
            "mean_reciprocal_rank": avg("reciprocal_rank_first_required"),
        }, "cases": rows}
    return {"annotation_status": annotations.get("status"), "results": output,
            "limitations": [
                "Only reviewed annotated cases are evaluated; results do not represent all 15 questions.",
                "Required concepts determine metrics; supporting concepts are reported separately.",
                "Precision@10 uses ten retrieval slots as denominator.",
                "MRR is based on first required concept, not completeness.",
                "No instance mapping, temporal data retrieval, or cross-domain join is validated."
            ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotations", type=Path, default=Path("experiments/vector_graph_rag/data/reviewed_concepts_q07.json"))
    ap.add_argument("--retrieval", type=Path, required=True)
    ap.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--output", type=Path, default=Path("experiments/vector_graph_rag/data/concept_eval_q07.json"))
    args = ap.parse_args()
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    report = evaluate(load(args.annotations), load(args.retrieval), load(args.index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({mode: value["summary"] for mode, value in report["results"].items()}, indent=2))
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
