#!/usr/bin/env python3
"""Regression smoke test for GraphDB-backed asset/product answers (no pytest required)."""
import argparse
import os
import sys

from ask_graphdb_ollama import answer

CASES = [
    ("TEP_XMEAS7", "product"),
    ("TEP_Reactor", "candidate"),
    ("TEP_Condenser", "candidate"),
    ("TEP_Compressor", "candidate"),
    ("TEP_XMEAS23", "unmapped"),
]


def check_case(label, kind, endpoint, ollama, model, evidence_only):
    result = answer(f"Which product is associated with {label}?", endpoint, ollama, model, evidence_only)
    matches = [x for x in result["evidence"] if x["asset"].get("label") == label]
    if len(matches) != 1 or len(result["evidence"]) != 1:
        return False, f"Expected one exact asset match, got {len(result['evidence'])}"
    record = matches[0]
    asset, product = record["asset"], record["matched_product"]
    if kind == "product":
        ok = bool(asset.get("productRef") and product and
                  asset["productRef"] == product.get("identifier"))
    elif kind == "candidate":
        ok = bool(not asset.get("productRef") and asset.get("candidateRef") and not product)
    else:
        ok = bool(not asset.get("productRef") and not asset.get("candidateRef") and not product)
    if not ok:
        return False, f"Unexpected reference mapping: {asset!r}, matched_product={product!r}"
    if not evidence_only:
        if result["status"] != "DETERMINISTIC_GROUNDED_RESPONSE":
            return False, f"Expected deterministic response, got {result['status']}"
        text = result["answer"]
        if label not in text:
            return False, "Answer does not name the asset"
        if kind == "product" and product["label"] not in text:
            return False, "Answer does not name matched product"
        if kind == "candidate" and "provisional" not in text.lower():
            return False, "Answer does not mark candidate as provisional"
    return True, result["answer"] or "GraphDB evidence validated"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv("GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--ollama", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    failed = 0
    for label, kind in CASES:
        try:
            passed, detail = check_case(label, kind, args.graphdb, args.ollama,
                                        args.model, args.evidence_only)
        except Exception as exc:
            passed, detail = False, str(exc)
        print(f"{'PASS' if passed else 'FAIL'} {label} [{kind}]: {detail}")
        failed += not passed
    print(f"Result: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
