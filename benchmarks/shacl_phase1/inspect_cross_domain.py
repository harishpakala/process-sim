"""Inspect cross-domain SHACL evidence before attempting query planning.

No Ollama call, synthetic SHACL edge, or inferred value equality is involved.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.dtwise.shacl_planner.grounding.cross_domain import MultiDomainGrounding
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import (
    _matches_schema_term,
)


def inspect(grounding, query):
    owners = {}
    for domain, index in grounding.indexes.items():
        owners[domain] = {
            uri for uri, shape in index.shapes.items()
            if any(_matches_schema_term(query, label)
                   for label in shape.get("labels", [])
                   if "shacl shape" not in label.casefold())
        }
    if any(not values for values in owners.values()):
        return {"status": "unresolved", "reason": "Missing explicit shape in one or more domains",
                "shape_anchors": {k: sorted(v) for k, v in owners.items()}}
    # Property names are derived from SHACL, not from benchmark scenario IDs.
    names_by_domain = []
    for domain, index in grounding.indexes.items():
        names_by_domain.append({
            p["name"].casefold(): p["name"]
            for owner in owners[domain] for p in index.properties.get(owner, [])
            if _matches_schema_term(query, p["name"])
        })
    common = set.intersection(*(set(names) for names in names_by_domain))
    evidence = {name: grounding.property_matches(name, owners) for name in sorted(common)}
    grounded = [name for name, result in evidence.items()
                if result["status"] == "grounded"]
    return {
        "status": "grounded" if len(grounded) == 1 else (
            "ambiguous" if grounded or common else "unresolved"),
        "shape_anchors": {k: sorted(v) for k, v in owners.items()},
        "property_evidence": evidence,
        "reason": "Evidence inspection only; no cross-domain plan has been selected",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path,
                        default=ROOT / "benchmarks/shacl_phase1/benchmark_queries.json")
    parser.add_argument("--schema", type=Path,
                        default=ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json")
    parser.add_argument("--scenario", action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("cross_domain_grounding.json"))
    args = parser.parse_args()
    scenarios = json.loads(args.benchmark.read_text(encoding="utf-8"))["scenarios"]
    selected = [s for s in scenarios if s["scenario_id"] in args.scenario]
    if len(selected) != len(set(args.scenario)):
        parser.error("Unknown or duplicate scenario ID")
    results = []
    for scenario in selected:
        domains = scenario["expected_semantics"]["domains"]
        grounding = MultiDomainGrounding.load(args.schema, domains)
        for variant in scenario["paraphrases"]:
            evidence = inspect(grounding, variant["query"])
            results.append({"id": variant["id"], "query": variant["query"], **evidence})
            print(f'{variant["id"]:<12} {evidence["status"]}')
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print("Evidence:", args.output)


if __name__ == "__main__":
    main()
