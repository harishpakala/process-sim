#!/usr/bin/env python3
"""Phase 6G: read-only catalog-only deterministic Q5 subquery. No cross-domain joins."""
import argparse
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
NS = "https://example.org/productcatalog/"
PRODUCT_FIELDS = {
    "manufacturer": "hasManufacturerName",
    "designation": "hasManufacturerProductDesignation",
    "eclass_class": "hasECLASSClass",
    "eclass_irdi": "hasECLASSIRDI",
    "eclass_verification": "hasECLASSVerificationStatus",
    "selection_status": "hasSelectionStatus",
    "installation_verification": "hasInstallationVerificationStatus",
}
PROPERTY_FIELDS = {
    "family_range": "hasFamilyMeasuringRange",
    "qudt_quantity_kind": "hasFamilyMeasuringRangeQUDTQuantityKind",
    "qudt_unit": "hasFamilyMeasuringRangeQUDTUnit",
    "maximum_pressure": "hasFamilyMaximumProcessPressure",
    "qualification": "hasApplicationQualification",
    "category": "hasProductCategory",
    "disclaimer": "hasSelectionDisclaimer",
}

def sparql_literal(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("Product identifier must be a nonempty printable string (max 2048 characters)")
    return json.dumps(value, ensure_ascii=True)

def compile_query(product_identifier):
    literal = sparql_literal(product_identifier)
    lines = [
        "PREFIX pc: <" + NS + ">",
        "SELECT DISTINCT ?product ?product_identifier ?properties " +
        " ".join("?" + key for key in (*PRODUCT_FIELDS, *PROPERTY_FIELDS)),
        "WHERE {",
        "  ?product pc:hasProductIdentifier ?product_identifier .",
        "  FILTER(isLiteral(?product_identifier) && STR(?product_identifier) = " + literal + ")",
        "  OPTIONAL { ?product pc:hasTechnicalProperties ?properties . }",
    ]
    for key, predicate in PRODUCT_FIELDS.items():
        lines.append("  OPTIONAL { ?product pc:" + predicate + " ?" + key + " . }")
    for key, predicate in PROPERTY_FIELDS.items():
        lines.append("  OPTIONAL { ?product pc:hasTechnicalProperties ?properties . "
                     "?properties pc:" + predicate + " ?" + key + " . }")
    lines.extend(["}", "ORDER BY STR(?product)"])
    return "\n".join(lines)

def execute(endpoint, query, timeout=30):
    response = requests.post(endpoint, data={"query": query},
                             headers={"Accept": "application/sparql-results+json"}, timeout=timeout)
    response.raise_for_status()
    return response.json()["results"]["bindings"]

def validate(product_identifier, endpoint, execute_query=True, timeout=30):
    query = compile_query(product_identifier)
    result = {
        "phase": "6G", "intent": "catalog_product_properties_only",
        "product_identifier": product_identifier,
        "scope": "product_catalog_only", "route_integrated": False,
        "full_q5_supported": False, "gold_status": "missing_not_scored",
        "verified_cross_domain_identity": False, "verified_physical_membership": False,
        "sparql": query, "status": "compiled",
        "limitations": [
            "No verified reactor-instrument-to-product-candidate association is established.",
            "ECLASS and QUDT values are recorded catalog metadata, not independently verified standards mappings.",
            "Missing optional fields do not imply absence outside the queried dataset.",
            "No installed asset, physical containment, or BOM membership is inferred.",
            "No router or GraphDB updates are performed.",
        ],
    }
    if execute_query:
        bindings = execute(endpoint, query, timeout)
        result.update(status="executed", binding_count=len(bindings), bindings=bindings)
        if not bindings:
            result["note"] = "No catalog product matches this identifier in the queried dataset."
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product-identifier", required=True)
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--skip-execution", action="store_true")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--output", type=Path, default=Path("reports/phase6g_q5_validation.json"))
    args = ap.parse_args(argv)
    try:
        report = validate(args.product_identifier, args.graphdb_url,
                          not args.skip_execution, args.timeout)
    except (ValueError, requests.RequestException, KeyError) as exc:
        print(type(exc).__name__ + ": " + str(exc))
        return 2
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Report:", path)
    print("Status:", report["status"])
    print("Full Q5 supported: no (cross-domain association not verified)")
    if "binding_count" in report:
        print("Bindings:", report["binding_count"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
