"""Inspect SHACL candidate discovery for DTwise B23-B25 without GraphDB or Ollama.

Run: python scripts/diagnose_dtwise_candidates.py --start 23 --end 25
Produces JSON with root exclusions, candidate paths, planner decisions, and
mapping-approval status. This tool never approves mappings or executes queries.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import _candidates
from process_sim.dtwise.cross_domain_projection import plan_cross_domain_projection
from process_sim.dtwise.legacy_join_adapter import _legacy_question

DEFAULT_SCHEMA = ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json"
DEFAULT_MANIFEST = ROOT / "frontend/public/dtwise-benchmark-manifest.json"


def analyze(question: str, schema: Schema, mappings: list[dict]) -> dict:
    roots = []
    for c in schema.concepts:
        if c.get("kind") != "shape" or not c.get("domain"):
            continue
        domain = str(c["domain"]).casefold()
        labels = {str(x).casefold() for x in c.get("labels", [])}
        accepted = domain in labels or f"tep_{domain}" in labels
        paths = schema.shacl_paths(c["uri"], max_depth=5, domain=c["domain"])
        roots.append({"domain": c["domain"], "uri": c["uri"],
                      "labels": c.get("labels", []), "accepted": accepted,
                      "structural_paths_at_depth_5": sum(bool(p[-1].get("to_shape")) for p in paths)})
    report = {"root_shapes": len(roots),
              "root_filter_accepted": sum(r["accepted"] for r in roots),
              "root_filter_excluded": [r for r in roots if not r["accepted"] and r["structural_paths_at_depth_5"]],
              "candidate_count_by_domain": {}, "candidate_paths": [],
              "discovery_status": "not_run", "mapping_status": "not_checked"}
    try:
        catalog = _candidates(schema)
    except Exception as exc:
        report["discovery_status"] = "error"
        report["discovery_error"] = str(exc)
        return report
    report["discovery_status"] = "ok"
    report["candidate_count_by_domain"] = dict(sorted(Counter(c["domain"] for c in catalog).items()))
    canonical, explicit = _legacy_question(question)
    report["canonical_question"] = canonical
    report["parsed_explicit_request"] = explicit
    # Keep all candidate paths for the domains mentioned in the question,
    # including paths the projection planner may reject.
    domains = {c["domain"] for c in catalog if re.search(r"(?<!\w)" + re.escape(c["domain"]) + r"(?!\w)", question, re.I)}
    report["candidate_paths"] = [
        {"domain": c["domain"], "root": c["root"], "end": c["end"],
         "predicates": c["predicates"],
         "terminal_properties": [p["predicate"] for p in c["terminal"]]}
        for c in catalog if c["domain"] in domains
    ]
    try:
        plan = plan_cross_domain_projection(canonical, catalog, schema)
    except Exception as exc:
        report["projection_status"] = "rejected"
        report["projection_error"] = str(exc)
        return report
    if plan is None:
        report["projection_status"] = "no_match"
        return report
    report["projection_status"] = "candidate_found"
    report["projection"] = plan
    source, target = plan["source"], plan["target"]
    matched = []
    for m in mappings:
        forward = (m.get("left_domain") == source["domain"] and
                   m.get("right_domain") == target["domain"] and
                   m.get("left_property") == source["key_predicate"] and
                   m.get("right_property") == target["key_predicate"])
        reverse = (m.get("right_domain") == source["domain"] and
                   m.get("left_domain") == target["domain"] and
                   m.get("right_property") == source["key_predicate"] and
                   m.get("left_property") == target["key_predicate"])
        if forward or reverse:
            matched.append({"id": m.get("id"), "verified": m.get("verified") is True,
                            "has_evidence_ids": bool(m.get("evidence_ids"))})
    report["mapping_matches"] = matched
    report["mapping_status"] = ("exactly_one_verified" if
        sum(m["verified"] and m["has_evidence_ids"] for m in matched) == 1 else
        "missing_or_ambiguous_verified_mapping")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--mappings", type=Path)
    parser.add_argument("--start", type=int, default=23)
    parser.add_argument("--end", type=int, default=25)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/dtwise_candidate_diagnostics.json")
    args = parser.parse_args()
    schema = Schema(args.schema)
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))
    mappings = json.loads(args.mappings.read_text(encoding="utf-8")) if args.mappings else []
    if not isinstance(mappings, list):
        parser.error("--mappings must contain a flat JSON array")
    results = {}
    for case in cases:
        match = re.fullmatch(r"B(\d+)(?:\.\d+)?", case.get("id", ""))
        if match and args.start <= int(match.group(1)) <= args.end:
            results[case["id"]] = {"question": case["question"],
                                    **analyze(case["question"], schema, mappings)}
            print(f'{case["id"]}: {results[case["id"]].get("projection_status", "discovery_error")} / '
                  f'{results[case["id"]]["mapping_status"]}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Diagnostic report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
