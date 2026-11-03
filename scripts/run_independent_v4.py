#!/usr/bin/env python3
"""Independent V4: scoped ProductCatalog evidence and guarded answers; frozen scripts unchanged."""
import argparse
import hashlib
import importlib.util
import json
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from process_sim.api.catalog_grounding import POLICY, flags, catalog_records

spec = importlib.util.spec_from_file_location("frozen_queries", ROOT / "scripts/tep_nexus_paper_queries.py")
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)


def scope_report(report):
    """Attach catalog records by exact product URI, not by fuzzy instrument names."""
    report = copy.deepcopy(report)
    catalog = report.get("engineering") or {}
    if not isinstance(catalog, dict):
        raise ValueError("Evidence report must include engineering ProductCatalog records")
    for qid in ("Q7", "Q10"):
        row = next(x for x in report["results"] if x["id"] == qid)
        evidence = row.get("evidence") or {}
        matches = {}
        for mapping in evidence.get("graphdb_verified_mappings", []):
            product = mapping.get("productId")
            for key, record in catalog.items():
                if isinstance(record, dict) and record.get("product_uri") == product:
                    matches[key] = copy.deepcopy(record)
        if not matches:
            raise ValueError(qid + ": no exact ProductCatalog match for productId")
        evidence["engineering_catalog"] = matches
        row["evidence"] = evidence
    q6 = next(x for x in report["results"] if x["id"] == "Q6")
    q6["evidence"]["graphdb_verified_mappings"] = [
        {k: v for k, v in m.items() if k != "eclassCode"}
        for m in q6["evidence"]["graphdb_verified_mappings"]]
    return report


def extra_flags(row):
    evidence = row.get("evidence") or {}
    answer = (row.get("ollama_answer") or {}).get("answer") or ""
    qid = row["id"]
    issues = []
    if qid == "Q6":
        for m in evidence.get("graphdb_verified_mappings", []):
            for key in ("assetId", "dexpiLocal", "ecadLocal", "productId"):
                value = m.get(key)
                if value and value not in answer and (key != "productId" or value.rsplit("/", 1)[-1] not in answer):
                    issues.append("MISSING_MAPPING_FIELD:" + key + ":" + value)
    if qid in ("Q7", "Q10"):
        records = catalog_records(evidence)
        for m in evidence.get("graphdb_verified_mappings", []):
            record = next((r for r in records if r.get("product_uri") == m.get("productId")), None)
            if record is None:
                issues.append("MISSING_PRODUCTCATALOG_JOIN")
            elif m.get("eclassCode") != record.get("eclass_class"):
                issues.append("GRAPHDB_PRODUCTCATALOG_CLASS_MISMATCH")
            if record and record.get("eclass_class") and record["eclass_class"] not in answer:
                issues.append("MISSING_PRODUCTCATALOG_CLASS")
    if qid == "Q9":
        for signal, samples in evidence.get("measurements", {}).items():
            if signal not in answer:
                issues.append("MISSING_SIGNAL:" + signal)
            for position in ("before", "after"):
                sample = samples.get(position) or {}
                if sample and (str(sample.get("value")) not in answer or
                               str(sample.get("simulation_seconds")) not in answer):
                    issues.append("MISSING_SAMPLE:" + signal + ":" + position)
    return issues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True)
    p.add_argument("--questions", default="reports/independent_questions_v2.json")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--output", default="reports/independent_v4_results.json")
    args = p.parse_args()
    report = scope_report(json.loads(Path(args.evidence).read_text(encoding="utf-8-sig")))
    questions = frozen.load_questions(args.questions)
    frozen.ANSWER_SYSTEM_PROMPT += "\n" + POLICY
    frozen.PROMPT_VERSION = "INDEPENDENT_V4_SCOPED_PRODUCTCATALOG"
    frozen.ANSWER_PROMPT_SHA256 = hashlib.sha256(
        frozen.ANSWER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    result = frozen.run(report, ollama_url=args.ollama_url, model=args.model,
                        questions=questions)
    counts = {"NO_DETECTED_ISSUES": 0, "REVIEW_REQUIRED": 0}
    for row in result["results"]:
        response = row.get("ollama_answer")
        if response is None:
            issues = ["MODEL_ANSWER_UNAVAILABLE"]
        else:
            issues = flags(response.get("answer"), response.get("limitations"),
                           row.get("evidence") or {}, row["id"])
        issues = sorted(set(issues + extra_flags(row)))
        row["productcatalog_validation"] = {
            "status": "REVIEW_REQUIRED" if issues else "NO_DETECTED_ISSUES",
            "flags": issues,
            "note": "Conservative heuristic checks; not proof of semantic correctness."
        }
        counts[row["productcatalog_validation"]["status"]] += 1
        if issues:
            # Preserve raw model answer for auditing; never silently mark it correct.
            row["rejected_model_answer"] = response
            row["accepted_answer"] = row["reference_answer"]
            row["accepted_answer_source"] = "DETERMINISTIC_EVIDENCE_FALLBACK"
        else:
            row["accepted_answer"] = response
            row["accepted_answer_source"] = "OLLAMA_HEURISTIC_CHECKS_PASSED"
    result["scope"] = "Independent Q1-Q10 fixed registry; exact ProductCatalog joins for Q7/Q10; Q6 mappings only; correctness not proven"
    result["productcatalog_validation_summary"] = counts
    result["questions_file"] = args.questions
    result["answer_generation_mode"] = "BLIND_EVIDENCE_ONLY_SCOPED_PRODUCTCATALOG"
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved", out, counts)
    for row in result["results"]:
        issues = row["productcatalog_validation"]["flags"]
        if issues:
            print(row["id"], ", ".join(issues))


if __name__ == "__main__":
    main()
