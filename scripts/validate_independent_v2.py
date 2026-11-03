#!/usr/bin/env python3
"""Conservative, read-only validation of independent Q1-Q10 Ollama outputs.

Does not change the frozen paper scripts or claim semantic correctness.
"""
import argparse
import json
import re
from pathlib import Path


def validate(row):
    evidence = row.get("evidence") or {}
    response = row.get("ollama_answer") or {}
    answer = response.get("answer", "")
    limitations = response.get("limitations", [])
    if not isinstance(answer, str) or not isinstance(limitations, list):
        return ["MISSING_OR_INVALID_MODEL_ANSWER"]
    warnings = []
    mappings = evidence.get("graphdb_verified_mappings", []) if isinstance(evidence, dict) else []
    if mappings:
        # The question registry determines the expected mapping coverage.
        for mapping in mappings:
            for field in ("assetId", "dexpiLocal", "ecadLocal", "signal", "productId", "eclassCode"):
                expected = mapping.get(field)
                if not expected:
                    continue
                required = {
                    "Q1": ("dexpiLocal",),
                    "Q2": ("ecadLocal",),
                    "Q3": ("assetId", "signal"),
                    "Q6": ("assetId", "dexpiLocal", "ecadLocal", "productId"),
                    "Q7": ("assetId", "dexpiLocal", "ecadLocal", "signal", "productId", "eclassCode"),
                    "Q10": ("assetId", "dexpiLocal", "ecadLocal", "signal", "productId", "eclassCode"),
                }.get(row["id"], ())
                if field in required and str(expected) not in answer:
                    # Product URIs can be shortened to the terminal catalog key.
                    if field != "productId" or str(expected).rsplit("/", 1)[-1] not in answer:
                        warnings.append("MISSING_REQUIRED_FIELD:" + field + ":" + str(expected))
        if row["id"] == "Q6":
            # IRDI and preferred-name values are not part of the mapping evidence.
            if re.search(r"\bIRDI\s*:", answer, re.I):
                warnings.append("UNSUPPORTED_IRDI_CLAIM")
            if re.search(r"\bpreferred name\s*:", answer, re.I):
                warnings.append("UNSUPPORTED_PREFERRED_NAME_CLAIM")
    if row["id"] in ("Q4", "Q5") and isinstance(evidence, dict):
        for record in evidence.values():
            if not isinstance(record, dict):
                continue
            if row["id"] == "Q4":
                if record.get("product_key") and record["product_key"] not in answer:
                    warnings.append("MISSING_PRODUCT:" + record["product_key"])
                if record.get("manufacturer") and record["manufacturer"] not in answer:
                    warnings.append("MISSING_MANUFACTURER:" + record["manufacturer"])
            else:
                for field in ("eclass_class", "eclass_irdi"):
                    if record.get(field) and str(record[field]) not in answer:
                        warnings.append("MISSING_" + field.upper() + ":" + str(record[field]))
    if row["id"] in ("Q9", "Q10"):
        temporal = evidence.get("temporal", evidence) if isinstance(evidence, dict) else {}
        measurements = temporal.get("measurements", {}) or {}
        if row["id"] == "Q10" and "before" in measurements:
            measurements = {temporal.get("signal", "XMEAS6"): measurements}
        combined = answer + " " + " ".join(str(x) for x in limitations)
        for signal, samples in measurements.items():
            if signal not in answer:
                warnings.append("MISSING_SIGNAL:" + signal)
            for position in ("before", "after"):
                sample = samples.get(position) if isinstance(samples, dict) else None
                if sample and str(sample["value"]) not in answer:
                    warnings.append("MISSING_SAMPLE:" + signal + ":" + position)
            if re.search(r"(?:no (?:information|data|evidence)|unavailable|missing)[^.\n]*\b" + re.escape(signal) + r"\b", combined, re.I) or re.search(r"\b" + re.escape(signal) + r"\b[^.\n]*(?:not (?:available|provided)|missing)", combined, re.I):
                warnings.append("CONTRADICTORY_MISSING_SIGNAL:" + signal)
    if row["id"] == "Q8":
        event = evidence.get("activation") or {}
        for field in ("fault_id", "action"):
            if event.get(field) and str(event[field]) not in answer:
                warnings.append("MISSING_EVENT_FIELD:" + field)
    return sorted(set(warnings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    summary = {"NO_DETECTED_ISSUES": 0, "REVIEW_REQUIRED": 0}
    for row in data["results"]:
        flags = validate(row)
        row["independent_v2_validation"] = {
            "status": "REVIEW_REQUIRED" if flags else "NO_DETECTED_ISSUES",
            "flags": flags,
            "note": "Heuristic checks only; no answer is automatically verified.",
        }
        summary[row["independent_v2_validation"]["status"]] += 1
    data["independent_v2_validation_summary"] = summary
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {path}; {summary['REVIEW_REQUIRED']} review required; "
          f"{summary['NO_DETECTED_ISSUES']} without detected issues (not verified)")
    for row in data["results"]:
        if row["independent_v2_validation"]["flags"]:
            print(row["id"] + ": " + ", ".join(row["independent_v2_validation"]["flags"]))


if __name__ == "__main__":
    main()
