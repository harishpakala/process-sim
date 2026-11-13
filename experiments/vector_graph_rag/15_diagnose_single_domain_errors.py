"""Diagnose single-domain property-selection errors without modifying retrieval/planner."""
import argparse
import json
from pathlib import Path

ROOT = Path("experiments/vector_graph_rag/data")


def diagnose(evaluation, retrieval, top=5):
    lookup = {r.get("question"): r for r in retrieval.get("results", [])}
    errors = []
    for case in evaluation.get("cases", []):
        if case.get("top_ranked_in_domain_correct"):
            continue
        question = case["question"]
        domain = case["domain"]
        gold = case["gold_property"]
        retrieval_row = lookup.get(question, {})
        hits = retrieval_row.get("hybrid", {}).get("hits", [])
        domain_properties = [
            {"global_rank": i, "uri": hit.get("uri"),
             "is_gold": hit.get("uri") == gold}
            for i, hit in enumerate(hits, 1)
            if hit.get("domain") == domain and hit.get("kind") == "property"
        ]
        gold_global_rank = next((i for i, h in enumerate(hits, 1)
                                 if h.get("domain") == domain and h.get("uri") == gold), None)
        gold_property_rank = next((i for i, h in enumerate(domain_properties, 1)
                                   if h["is_gold"]), None)
        errors.append({
            "question": question,
            "domain": domain,
            "gold_property": gold,
            "selected_property": case.get("selected_property"),
            "gold_global_top_k_rank": gold_global_rank,
            "gold_rank_among_domain_properties": gold_property_rank,
            "top_domain_property_candidates": domain_properties[:top],
            "planner_status": case.get("planner_status"),
            "planner_reason": case.get("planner_reason"),
            "diagnosis": (
                "Expected property retrieved but ranked below another in-domain property"
                if gold_property_rank and gold_property_rank > 1
                else "No expected property in eligible in-domain property hits"
            ),
        })
    return {"error_count": len(errors), "errors": errors,
            "note": "Ranking diagnosis only; semantic equivalence requires expert review."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=ROOT / "single_domain_evaluation.json")
    parser.add_argument("--retrieval", type=Path, default=ROOT / "hybrid_evaluation_33_v3.json")
    parser.add_argument("--output", type=Path, default=ROOT / "single_domain_error_diagnostics.json")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    retrieval = json.loads(args.retrieval.read_text(encoding="utf-8"))
    result = diagnose(evaluation, retrieval, args.top)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
