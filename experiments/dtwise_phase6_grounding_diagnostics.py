#!/usr/bin/env python3
"""Phase 6A: read-only shape/predicate grounding diagnostics for V4.1 audits.

Does not repair plans, invent joins, or declare a predicate valid because it
appears on another shape. Evidence and connectivity require separate checks.
"""
import argparse
import json
from pathlib import Path


def diagnose(audit):
    catalog = audit.get("candidate_shapes") or {}
    plan = audit.get("plan") or {}
    findings = []
    for section in ("fields", "filters"):
        for index, field in enumerate(plan.get(section) or []):
            if not isinstance(field, dict):
                continue
            predicate, selected = field.get("predicate"), field.get("shape")
            if not isinstance(predicate, str):
                continue
            owners = sorted(
                shape_id for shape_id, shape in catalog.items()
                if any(isinstance(prop, dict) and prop.get("predicate") == predicate
                       for prop in (shape.get("properties") or []))
            )
            valid = selected in owners
            findings.append({
                "section": section, "index": index, "name": field.get("name"),
                "predicate": predicate, "selected_shape": selected,
                "declared_on_selected_shape": valid,
                "other_candidate_shapes": [s for s in owners if s != selected],
                "classification": (
                    "valid_on_selected_shape" if valid else
                    "declared_on_other_candidate_shape" if owners else
                    "absent_from_candidate_schema"
                ),
                "auto_repaired": False,
                "join_verified": False,
            })
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audits", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    for path in args.audits:
        audit = json.loads(path.read_text(encoding="utf-8"))
        findings = diagnose(audit)
        results.append({"audit_file": str(path), "question": audit.get("question"),
                        "findings": findings})
        for item in findings:
            if item["classification"] != "valid_on_selected_shape":
                print(f"{path.name}: {item['classification']}: {item['predicate']} "
                      f"on {item['selected_shape']} (other candidates: "
                      f"{', '.join(item['other_candidate_shapes']) or 'none'})")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"cases": results}, indent=2) + "\n", encoding="utf-8")
        print("Audit:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
