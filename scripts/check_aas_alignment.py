#!/usr/bin/env python3
"""Check AAS template/instance structural alignment before semantic lifting.

Uses only the Python standard library; no GraphDB connection required.
A mismatch is reported, never silently repaired or converted into invented RDF.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ("dexpi", "semantic/templates/dexpi_template.json", "examples/aas/tep_dexpi_instance.json"),
    ("ecad", "semantic/templates/ecad_template.json", "examples/aas/tep_ecad_instance.json"),
    ("productcatalog", "semantic/templates/product_catalog_template.json", "examples/aas/product_catalog_instance.json"),
    ("assetinventory", "semantic/templates/asset_inventory_template.json", "examples/aas/asset_inventory_instance.json"),
)

def children(element):
    return element.get("value", []) if element.get("modelType") == "SubmodelElementCollection" else []

def cardinality(element):
    return next((q.get("value") for q in element.get("qualifiers", []) if q.get("type") == "Cardinality"), None)

def check(template, instance, path="", issues=None):
    if issues is None:
        issues = []
    expected = template.get("submodelElements", []) if not path else children(template)
    actual = instance.get("submodelElements", []) if not path else children(instance)
    template_by_id = {e.get("idShort"): e for e in expected}
    actual_by_id = {e.get("idShort"): e for e in actual}
    repeatable = [e for e in expected if cardinality(e) in ("ZeroToMany", "OneToMany")]
    for name, element in template_by_id.items():
        if name in actual_by_id:
            matched = actual_by_id[name]
            if matched.get("modelType") != element.get("modelType"):
                issues.append(f"{path}/{name}: expected {element.get('modelType')}, got {matched.get('modelType')}")
            elif element.get("modelType") == "SubmodelElementCollection":
                check(element, matched, path + "/" + name, issues)
        elif cardinality(element) in ("One", "OneToMany"):
            # Repeatable placeholders may have concrete instance idShort values.
            if element not in repeatable or not actual:
                issues.append(f"{path}/{name}: missing required element")
    for name, element in actual_by_id.items():
        if name in template_by_id:
            continue
        if len(repeatable) == 1 and element.get("modelType") == repeatable[0].get("modelType"):
            check(repeatable[0], element, path + "/" + name, issues)
        else:
            issues.append(f"{path}/{name}: not declared by template")
    return issues

def main():
    selected = set(sys.argv[1:])
    failures = 0
    for domain, template_path, instance_path in TARGETS:
        if selected and domain not in selected:
            continue
        template = json.loads((ROOT / template_path).read_text(encoding="utf-8"))
        instance = json.loads((ROOT / instance_path).read_text(encoding="utf-8"))
        issues = check(template, instance)
        if issues:
            failures += 1
            print(f"[MISMATCH] {domain}: {len(issues)} issue(s)")
            for issue in issues[:30]:
                print("  - " + issue)
            if len(issues) > 30:
                print(f"  ... {len(issues) - 30} more")
        else:
            print(f"[OK] {domain}: structural alignment")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
