#!/usr/bin/env python3
"""Evaluate Q1-Q12 together with source-backed, evidence-conditioned Ollama QA.

Run from the process-sim repository root. Existing ten-question records are
left unchanged. This does NOT execute the live VTKG pipeline or auto-grade.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Recorded simulation run UUID")
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", default="reports/evaluation_12_2026")
    args = parser.parse_args()
    if not 0 <= args.start_seconds <= args.end_seconds or not 1 <= args.limit <= 5000:
        parser.error("Require 0 <= start <= end and 1 <= limit <= 5000.")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN must be set locally; do not commit credentials.")

    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, str(ROOT / "scripts/tep_nexus_e4e_compare.py"),
        "--run-id", args.run_id,
        "--graphdb-url", args.graphdb_url,
        "--output-root", str(output / "evidence"),
        "--asset-inventory", str(ROOT / "examples/aas/asset_inventory_instance.json"),
        "--product-catalog", str(ROOT / "examples/aas/product_catalog_instance.json"),
    ], check=True, cwd=ROOT)

    evidence_file = output / "evidence/revised/evidence_and_assessment_template.json"
    report = json.loads(evidence_file.read_text(encoding="utf-8"))
    rows = report["results"]
    if [r["id"] for r in rows] != [f"Q{i}" for i in range(1, 11)]:
        raise RuntimeError("Expected exactly the existing revised Q1-Q10 question set.")

    evaluator = load_module("scripts/tep_nexus_paper_evaluation.py", "paper_eval_12")
    qa = load_module("scripts/tep_nexus_e4e_ollama_qa.py", "ollama_qa_12")
    engineering = evaluator.engineering_evidence(
        str(ROOT / "examples/aas/asset_inventory_instance.json"),
        str(ROOT / "examples/aas/product_catalog_instance.json"))
    temperature = engineering["temperature"]
    if temperature["equipment_tag"] != "TI-1101" or temperature["signal"] != "XMEAS9":
        raise RuntimeError("TI-1101 to XMEAS9 mapping differs from the test fixture.")

    q11 = {
        "source": "AAS AssetInventory and ProductCatalog instances",
        "asset_id": temperature.get("asset_id"),
        "equipment_tag": temperature.get("equipment_tag"),
        "product_uri": temperature.get("product_uri"),
        "product_key": temperature.get("product_key"),
        "eclass_class": temperature.get("eclass_class"),
        "eclass_irdi": temperature.get("eclass_irdi"),
        "eclass_verification": temperature.get("eclass_verification"),
        "product_selection_status": temperature.get("product_selection_status"),
        "installation_verification": temperature.get("installation_verification"),
    }

    import psycopg
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            samples = conn.execute("""
                SELECT simulation_time_hours, value, observed_at
                FROM public.signal_samples
                WHERE run_id = %s::uuid AND signal_id = %s
                  AND simulation_time_hours >= %s
                  AND simulation_time_hours <= %s
                ORDER BY simulation_time_hours, observed_at
                LIMIT %s
            """, (args.run_id, "XMEAS9", args.start_seconds / 3600,
                  args.end_seconds / 3600, args.limit + 1)).fetchall()
    truncated = len(samples) > args.limit
    q12 = {
        "source": "TimescaleDB public.signal_samples (read-only)",
        "mapping_source": "AAS AssetInventory instance",
        "asset_id": temperature.get("asset_id"),
        "equipment_tag": "TI-1101",
        "signal": "XMEAS9",
        "run_id": args.run_id,
        "interval_seconds_inclusive": [args.start_seconds, args.end_seconds],
        "truncated": truncated,
        "observations": [
            {"simulation_seconds": float(t) * 3600, "value": float(v),
             "observed_at": ts.isoformat()}
            for t, v, ts in samples[:args.limit]
        ],
        "qualification": "Direct historian evidence, not VTKG-to-SQL equivalence.",
    }
    rows += [
        {"id": "Q11", "question":
         "Which ECLASS IRDI is associated with the product candidate linked to the reactor temperature instrument TI-1101?",
         "evidence_status": "EVIDENCE_AVAILABLE" if q11["eclass_irdi"] else "NO_EVIDENCE",
         "evidence": q11},
        {"id": "Q12", "question":
         f"What recorded temperature observations are associated with TI-1101 during simulation time {args.start_seconds:g} to {args.end_seconds:g} seconds in the selected run?",
         "evidence_status": "EVIDENCE_AVAILABLE" if q12["observations"] else "NO_EVIDENCE",
         "evidence": q12},
    ]

    destination = output / "answers_12.json"
    results = []
    for row in rows:
        evidence = row.get("evidence")
        prompt = ("Question:\n" + row["question"] +
                  "\n\nEvidence from a read-only snapshot (JSON):\n" +
                  json.dumps(evidence, indent=2, ensure_ascii=False, default=str) +
                  "\n\nGive a grounded answer. Note missing evidence and timing discrepancies.")
        entry = {
            "id": row["id"], "question": row["question"],
            "evidence_status": row.get("evidence_status"),
            "evidence_sha256": hashlib.sha256(
                json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest(),
            "answer_text": None, "model_metadata": None,
            "manual_assessment": None, "assessment_justification": None, "error": None,
        }
        try:
            entry["answer_text"], entry["model_metadata"] = qa.request_ollama(
                args.ollama_url, args.model, prompt, args.timeout)
            print(f'{row["id"]}: answer saved', flush=True)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            print(f'{row["id"]}: ERROR: {exc}', flush=True)
        results.append(entry)
        destination.write_text(json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": args.run_id,
            "model_requested": args.model,
            "method": "evidence_conditioned_ollama_qa_not_live_vtkg_execution",
            "assessment_status": "NOT_MANUALLY_ASSESSED",
            "q11_evidence": q11, "q12_evidence": q12,
            "results": results,
        }, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Saved {destination}; {len(results)} questions; no automatic grades.")


if __name__ == "__main__":
    main()
