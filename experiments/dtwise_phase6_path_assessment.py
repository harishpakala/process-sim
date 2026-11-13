#!/usr/bin/env python3
"""Phase 6B: fail-closed assessment of alternative SHACL shape candidates.

V4.1 join_candidates are *identifier equality hypotheses*, not verified
cross-domain relationships. This tool never rewrites plans or executes SPARQL.
"""
import argparse
import json
from collections import deque
from pathlib import Path

try:
    from experiments.dtwise_phase6_grounding_diagnostics import diagnose
except ModuleNotFoundError:
    from dtwise_phase6_grounding_diagnostics import diagnose


def hypothesis_path(edges, start, target):
    """Return a shortest path of candidate edge IDs, or None."""
    if start == target:
        return []
    queue = deque([(start, [])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        for edge_id, edge in sorted(edges.items()):
            if not isinstance(edge, dict):
                continue
            left, right = edge.get("left"), edge.get("right")
            nxt = right if node == left else left if node == right else None
            if nxt is None or nxt in visited:
                continue
            new_path = path + [edge_id]
            if nxt == target:
                return new_path
            visited.add(nxt)
            queue.append((nxt, new_path))
    return None


def assess(audit):
    edges = audit.get("join_candidates") or {}
    findings = diagnose(audit)
    for item in findings:
        candidates = []
        for alternative in item["other_candidate_shapes"]:
            path = hypothesis_path(edges, item["selected_shape"], alternative)
            candidates.append({
                "shape": alternative,
                "hypothesis_path": path,
                "connectivity": "candidate_equality_path" if path is not None else "no_candidate_path",
                "verified_evidence": False,
                "eligible_for_automatic_repair": False,
            })
        item["alternatives_assessed"] = candidates
        item["repair_decision"] = (
            "no_repair_needed" if item["declared_on_selected_shape"] else
            "unsupported_in_candidate_schema" if not candidates else
            "ambiguous_unverified_alternatives"
        )
        item["join_verified"] = False
        item["auto_repaired"] = False
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audits", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = []
    for path in args.audits:
        audit = json.loads(path.read_text(encoding="utf-8"))
        findings = assess(audit)
        cases.append({"audit_file": str(path), "question": audit.get("question"),
                      "findings": findings})
        for finding in findings:
            if finding["repair_decision"] != "no_repair_needed":
                print(f"{path.name}: {finding['repair_decision']}: "
                      f"{finding['predicate']} on {finding['selected_shape']}")
                for alt in finding["alternatives_assessed"]:
                    print(f"  alternative {alt['shape']}: {alt['connectivity']} "
                          f"{alt['hypothesis_path']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "policy": "diagnostic_only_no_verified_cross_domain_joins",
            "limitations": [
                "Candidate equality joins do not prove shared engineering identity.",
                "A path through candidate joins is not verified ontology evidence.",
                "No automatic plan repair, ontology modification, or GraphDB execution.",
            ],
            "cases": cases,
        }, indent=2) + "\n", encoding="utf-8")
        print("Audit:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
