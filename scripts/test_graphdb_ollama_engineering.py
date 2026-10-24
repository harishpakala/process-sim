#!/usr/bin/env python3
"""Exercise Ollama's free-form engineering answers using live GraphDB evidence.

These are review cases, not a claim of automatic engineering correctness.
"""
import argparse
import json
import os
import sys

from ask_graphdb_ollama import answer

CASES = [
    {
        "name": "reactor-pressure-suitability",
        "question": "Why is the proposed TEP_Reactor candidate unsuitable for the current operating pressure?",
        "required_asset": "TEP_Reactor",
        "review": "Fact-guarded: must mention REQUIRES_ALTERNATIVE, avoid invented pressure ratings, and acknowledge missing numerical pressure evidence.",
    },
    {
        "name": "condenser-engineering-approval",
        "question": "Is TEP_Condenser engineering-approved and installed? Explain the evidence limits.",
        "required_asset": "TEP_Condenser",
        "review": "Must distinguish PROVISIONAL_CANDIDATE from approval/installation; no invented sizing.",
    },
    {
        "name": "compressor-technical-fit",
        "question": "Can you confirm the compressor map, gas compatibility and driver sizing for TEP_Compressor?",
        "required_asset": "TEP_Compressor",
        "review": "Must explicitly state these details cannot be confirmed from retrieved evidence.",
    },
    {
        "name": "pressure-transmitter-classification",
        "question": "Explain the ECLASS classification and verification status of TEP_XMEAS7.",
        "required_asset": "TEP_XMEAS7",
        "review": "Must identify 27-27-49-05, pressure transmitter and pending ECLASS verification; no installed-hardware claim.",
    },
    {
        "name": "unmapped-logical-measurement",
        "question": "Does TEP_XMEAS23 have a selected physical product, and can we infer one?",
        "required_asset": "TEP_XMEAS23",
        "review": "Fact-guarded: must state both ProductReference and CandidateProductReference are absent; no inferred physical product.",
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv("GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--ollama", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    errors = 0
    for case in CASES:
        try:
            result = answer(case["question"], args.graphdb, args.ollama, args.model,
                            evidence_only=args.evidence_only)
            labels = [item["asset"].get("label") for item in result["evidence"]]
            grounded = labels == [case["required_asset"]]
            freeform = (args.evidence_only or result["status"] == "GROUNDED_RESPONSE" or
                        (case["name"] in ("reactor-pressure-suitability", "unmapped-logical-measurement")
                         and result["status"] == "FACT_GUARDED_RESPONSE"))
            content = (result["answer"] or "").lower()
            semantic_ok = True
            if not args.evidence_only:
                if case["name"] == "reactor-pressure-suitability":
                    semantic_ok = "requires_alternative" in content
                elif case["name"] == "unmapped-logical-measurement":
                    semantic_ok = (
                        "no selected product" in content or "no productreference" in content
                    ) and not any(phrase in content for phrase in (
                        "candidate is present", "candidate product is present",
                        "candidateproductreference is present", "provisional candidate product",
                        "a candidate exists", "candidate was found",
                    ))
                elif case["name"] == "pressure-transmitter-classification":
                    semantic_ok = all(term in content for term in (
                        "27-27-49-05", "pressure transmitter", "pending_eclass_verification"
                    ))
            if not grounded or not freeform or not semantic_ok:
                errors += 1
            print(f"\n{'EVIDENCE PASS' if grounded and freeform and semantic_ok else 'FAIL'} {case['name']}")
            print("Question:", case["question"])
            print("Retrieved assets:", labels)
            print("Response status:", result["status"])
            print("Answer:", result["answer"] if result["answer"] is not None else "(evidence-only)")
            print("MANUAL REVIEW:", case["review"])
        except Exception as exc:
            errors += 1
            print(f"\nFAIL {case['name']}: {exc}")
    print(f"\nAutomated check failures: {errors}; cases: {len(CASES)}")
    if not args.evidence_only:
        print("IMPORTANT: Read each answer against MANUAL REVIEW criteria. "
              "No automatic correctness score is claimed for model-generated text.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
