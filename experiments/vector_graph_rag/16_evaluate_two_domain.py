"""Focused EngineeringBOM–ECAD two-domain governance smoke evaluation.

Uses existing deterministic N-domain planner and actual catalog/index.
No mappings are approved, changed, or executed by this experiment.
Run: python -m experiments.vector_graph_rag.16_evaluate_two_domain
"""
import argparse
import json
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain, _normalize

INDEX = Path("semantic/ontology/dtwise/dtwise-schema-index.json")
CATALOG = Path("semantic/ontology/dtwise/cross-domain-mappings.json")
OUTPUT = Path("experiments/vector_graph_rag/data/two_domain_governance_report.json")
QUESTION = "Which EngineeringBOM records correspond to ECAD electrical devices?"
CASES = [
    ("engineeringbom_ecad_candidate", ["engineeringbom", "ecad"], "abstained", "ready"),
    ("uncataloged_ecad_dexpi", ["ecad", "dexpi"], "abstained", "abstained"),
    ("uncataloged_engineeringbom_assetinventory", ["engineeringbom", "assetinventory"], "abstained", "abstained"),
]


def evaluate(index, catalog):
    plans = _normalize(catalog)
    results = []
    for case_id, domains, strict_expected, exploratory_expected in CASES:
        exact = [p for p in plans if set(p["domains"]) == set(domains)]
        modes = {}
        for mode, allow_candidate, expected in (
            ("strict", False, strict_expected),
            ("exploratory", True, exploratory_expected),
        ):
            try:
                plan = compile_n_domain(
                    QUESTION, index, catalog, set(domains), allow_candidate, 100, _validate_path
                )
            except ValueError as exc:
                status, reason, sparql, mapping_status = "abstained", str(exc), None, None
            else:
                status, reason = "ready", None
                sparql, mapping_status = plan["sparql"], plan["mapping_status"]
            modes[mode] = {
                "status": status, "expected": expected, "matches_expected": status == expected,
                "reason": reason, "mapping_status": mapping_status,
                "sparql": sparql, "executed": False,
            }
        results.append({
            "id": case_id, "domains": domains,
            "catalog_plan_ids": [p["id"] for p in exact],
            "catalog_statuses": [p["status"] for p in exact],
            "modes": modes,
        })
    total = sum(len(r["modes"]) for r in results)
    matched = sum(m["matches_expected"] for r in results for m in r["modes"].values())
    return {
        "evaluation_type": "two_domain_catalog_governance_smoke_test",
        "question": QUESTION,
        "summary": {
            "cases": len(results), "mode_checks": total, "expectation_matches": matched,
            "all_expectations_met": matched == total,
            "strict_ready": sum(r["modes"]["strict"]["status"] == "ready" for r in results),
            "exploratory_ready": sum(r["modes"]["exploratory"]["status"] == "ready" for r in results),
        },
        "limitations": [
            "Domains are explicitly supplied, not inferred from the question.",
            "Only catalog governance and schema-path validation are tested.",
            "The candidate mapping has not received semantic approval.",
            "Exploratory SPARQL is provisional and is not executed.",
            "No verified/approved mapping success is asserted or simulated.",
        ],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.index.read_text(encoding="utf-8")),
        json.loads(args.catalog.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    for row in result["results"]:
        print(row["id"] + ": " + ", ".join(
            mode + "=" + value["status"] + (" (" + value["reason"] + ")" if value["reason"] else "")
            for mode, value in row["modes"].items()
        ))
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
