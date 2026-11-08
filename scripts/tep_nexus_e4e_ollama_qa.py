#!/usr/bin/env python3
"""Run E4-E questions against local Ollama with evidence from existing reports.

This is evidence-conditioned LLM QA, NOT execution of the TEP NEXUS retrieval pipeline.
No automated correctness scoring, no simulation writes, no frozen-baseline modifications.
"""

# Created: 2026-11-03
# Author: Harish
import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = (
    "You are answering engineering questions using only the supplied evidence. "
    "Do not invent identifiers, measured values, times, product verification, or fault effects. "
    "Distinguish a recorded operator injection command from independently verified fault activation. "
    "Product-catalog attributes are not proof of physical instrument installation. "
    "If the evidence is insufficient or conflicts with the question, explicitly say so. "
    "Do not claim an event occurred at 30 seconds when its recorded simulation time differs. "
    "Answer the question concisely, with relevant evidence details."
)

def request_ollama(base_url, model, prompt, timeout):
    body = json.dumps({
        "model": model,
        "stream": False,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "options": {"temperature": 0, "seed": 42}
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.load(response)
    answer = data.get("message", {}).get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama returned no answer content")
    return answer, {key: data.get(key) for key in (
        "model", "created_at", "done", "total_duration", "eval_count",
        "prompt_eval_count")}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", choices=["original", "revised", "both"], default="both")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--evidence-root", default="reports/e4e_comparison")
    p.add_argument("--output-root", default="reports/e4e_llm")
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()
    variants = ["original", "revised"] if args.variant == "both" else [args.variant]
    reports = {}
    for variant in variants:
        path = ROOT / args.evidence_root / variant / "evidence_and_assessment_template.json"
        if not path.is_file():
            p.error(f"Missing {path}. Run tep_nexus_e4e_compare.py first.")
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("version") != variant or len(report.get("results", [])) != 10:
            p.error(f"Invalid report for {variant}: {path}")
        reports[variant] = report
    if len(reports) == 2 and reports["original"]["run_id"] != reports["revised"]["run_id"]:
        p.error("Original and revised evidence reports must use the same simulation run ID.")
    for variant in variants:
        evidence_report = reports[variant]
        question_path = ROOT / "docs" / "e4e_tests" / (variant + "_questions.json")
        questions = json.loads(question_path.read_text(encoding="utf-8"))["questions"]
        evidence_rows = evidence_report["results"]
        if [q["id"] for q in questions] != [f"Q{i}" for i in range(1, 11)]:
            p.error(f"Question registry invalid: {question_path}")
        if [r["id"] for r in evidence_rows] != [q["id"] for q in questions]:
            p.error(f"Evidence/question IDs differ for {variant}")
        output = ROOT / args.output_root / variant / "answers.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        results = []
        for q, evidence_row in zip(questions, evidence_rows):
            prompt = (
                "Question:\n" + q["question"] +
                "\n\nEvidence from a read-only snapshot (JSON):\n" +
                json.dumps(evidence_row.get("evidence"), ensure_ascii=False, indent=2) +
                "\n\nGive a grounded answer. Note missing evidence and timing discrepancies."
            )
            record = {
                "id": q["id"], "question": q["question"],
                "evidence_status": evidence_row.get("evidence_status"),
                "evidence_sha256": hashlib.sha256(json.dumps(
                    evidence_row.get("evidence"), sort_keys=True).encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(
                    (SYSTEM + "\n" + prompt).encode()).hexdigest(),
                "answer_text": None, "model_metadata": None,
                "manual_assessment": None, "assessment_justification": None,
                "error": None
            }
            try:
                record["answer_text"], record["model_metadata"] = request_ollama(
                    args.ollama_url, args.model, prompt, args.timeout)
                print(f"{variant} {q['id']}: answer saved", flush=True)
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
                record["error"] = str(exc)
                print(f"{variant} {q['id']}: ERROR: {exc}", flush=True)
            results.append(record)
            payload = {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "variant": variant, "run_id": evidence_report["run_id"],
                "model_requested": args.model,
                "method": "ollama_evidence_conditioned_qa_not_tep_nexus_retrieval_pipeline",
                "system_prompt": SYSTEM,
                "answer_correctness": "NOT_ASSESSED",
                "results": results
            }
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        print(f"Saved {output}", flush=True)

if __name__ == "__main__":
    main()
