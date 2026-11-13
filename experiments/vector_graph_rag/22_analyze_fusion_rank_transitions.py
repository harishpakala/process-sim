"""Analyze required-concept rank transitions in the six-question fusion ablation.

Reads the saved ablation JSON only; does not rerun retrieval or optimize weights.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent
DEFAULT_WEIGHTS = ("0.7", "0.75", "0.9", "1")


def analyze(data, weights):
    by_weight = data["results_by_weight"]
    missing = [w for w in weights if w not in by_weight]
    if missing:
        raise ValueError("Missing ablation weights: " + ", ".join(missing))
    by_case = {}
    for w in weights:
        cases = by_weight[w]["hybrid"]["cases"]
        by_case[w] = {c["id"]: c for c in cases if c["status"] == "scored"}
    ids = data["reviewed_question_ids"]
    if any(set(by_case[w]) != set(ids) for w in weights):
        raise ValueError("Missing scored question(s) at one or more weights")
    rows = []
    for qid in ids:
        concepts = {}
        for w in weights:
            for c in by_case[w][qid]["required_ranks"]:
                key = (c["domain"], c["uri"])
                concepts.setdefault(key, {})[w] = c["rank"]
        for (domain, uri), ranks in sorted(concepts.items()):
            if any(w not in ranks for w in weights):
                raise ValueError(f"Required concept set differs across weights: {qid} {uri}")
            changes = []
            for a, b in zip(weights, weights[1:]):
                ra, rb = ranks[a], ranks[b]
                changes.append({
                    "from_weight": float(a), "to_weight": float(b),
                    "from_rank": ra, "to_rank": rb,
                    "delta_rank": (rb - ra if ra is not None and rb is not None else None),
                    "entered_top_10": (ra is None or ra > 10) and rb is not None and rb <= 10,
                    "left_top_10": ra is not None and ra <= 10 and (rb is None or rb > 10),
                })
            rows.append({"question_id": qid, "domain": domain, "uri": uri,
                         "ranks": ranks, "transitions": changes})
    transitions = []
    for a, b in zip(weights, weights[1:]):
        entering = [r for r in rows if next(t for t in r["transitions"]
                    if t["from_weight"] == float(a) and t["to_weight"] == float(b))["entered_top_10"]]
        leaving = [r for r in rows if next(t for t in r["transitions"]
                    if t["from_weight"] == float(a) and t["to_weight"] == float(b))["left_top_10"]]
        transitions.append({
            "from_weight": float(a), "to_weight": float(b),
            "entered_top_10": [{"question_id": r["question_id"], "domain": r["domain"],
                                "uri": r["uri"], "from_rank": r["ranks"][a],
                                "to_rank": r["ranks"][b]} for r in entering],
            "left_top_10": [{"question_id": r["question_id"], "domain": r["domain"],
                             "uri": r["uri"], "from_rank": r["ranks"][a],
                             "to_rank": r["ranks"][b]} for r in leaving],
        })
    return {
        "analysis": "descriptive_in_sample_required_concept_rank_transitions",
        "weights": [float(w) for w in weights],
        "reviewed_question_ids": ids,
        "concepts": rows,
        "transitions": transitions,
        "limitations": [
            "Weights were examined on the same six reviewed development questions.",
            "Rank transitions do not establish a causal mechanism or a held-out optimum.",
            "Missing rank means absent from the saved top-k hits, not necessarily absent from the full index.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ablation", type=Path, default=ROOT / "data/concept_fusion_ablation_6.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/concept_fusion_rank_transitions_6.json")
    ap.add_argument("--weights", nargs="+", default=DEFAULT_WEIGHTS)
    args = ap.parse_args()
    data = json.loads(args.ablation.read_text(encoding="utf-8-sig"))
    output = analyze(data, args.weights)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("Per-required-concept ranks (None = not in saved top-k):")
    print("question  concept                               " + "  ".join(f"w={w}" for w in args.weights))
    for r in output["concepts"]:
        label = r["uri"].split("/")[-1]
        print(f"{r['question_id']:<8}  {label:<36} " +
              "  ".join(f"{str(r['ranks'][w]):>5}" for w in args.weights))
    for t in output["transitions"]:
        print(f"\n{t['from_weight']:g} -> {t['to_weight']:g}: "
              f"entered top 10={len(t['entered_top_10'])}, left top 10={len(t['left_top_10'])}")
        for event in ("entered_top_10", "left_top_10"):
            for c in t[event]:
                print(f"  {event}: {c['question_id']} {c['uri']} "
                      f"{c['from_rank']} -> {c['to_rank']}")
    print("\nDescriptive development-set analysis; no optimal weight claimed.")
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
