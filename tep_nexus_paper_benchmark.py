#!/usr/bin/env python3
"""Read-only paper benchmark runner for the four reactor measurements.

Uses the repository's existing planner; does not fabricate cross-domain joins,
run identifiers, fault events, or ground-truth answers.
"""

# Created: 2026-11-02
# Author: Harish
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SENSORS = {
    "pressure": {"tag": "PI-1101", "asset": "TEP_XMEAS7", "signal": "XMEAS7"},
    "flow": {"tag": "FI-1101", "asset": "TEP_XMEAS6", "signal": "XMEAS6"},
    "temperature": {"tag": "TI-1101", "asset": "TEP_XMEAS9", "signal": "XMEAS9"},
    "level": {"tag": "LI-1101", "asset": "TEP_XMEAS8", "signal": "XMEAS8"},
}

QUESTIONS = [
    ("Q1", "Which instruments are associated with the reactor?", ["DEXPI"]),
    ("Q2", "What are their electrical references?", ["DEXPI", "ECAD"]),
    ("Q3", "What are their asset IDs and signal references?", ["DEXPI", "AssetInventory"]),
    ("Q4", "Which products and manufacturers are associated with these assets?", ["AssetInventory", "ProductCatalog"]),
    ("Q5", "What are their ECLASS and QUDT attributes?", ["ProductCatalog"]),
    ("Q6", "Which BOM entries correspond to these instruments?", ["BOM", "AssetInventory"]),
    ("Q7", "What engineering information is available for PI-1101?", ["DEXPI", "ECAD", "BOM", "AssetInventory", "ProductCatalog"]),
    ("Q8", "Which fault was activated, and when?", ["fault_records"]),
    ("Q9", "What were the four sensor values before and after activation?", ["AssetInventory", "TimescaleDB", "fault_records"]),
    ("Q10", "What engineering and operational evidence is available for FI-1101?", ["DEXPI", "ECAD", "BOM", "AssetInventory", "ProductCatalog", "TimescaleDB", "fault_records"]),
]


def load_json(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Verified simulation historian run ID")
    parser.add_argument("--planner", default="scripts/tep_nexus_ollama_query_planner.py")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--output-dir", default="reports/tep_nexus_paper")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--reference", help="Optional JSON file of independently verified expected answers, keyed Q1..Q10")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    planner = Path(args.planner)
    if not planner.is_file():
        parser.error(f"Planner not found: {planner}. Run from the process-sim repository root.")
    references = load_json(args.reference) if args.reference else {}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "model": args.model,
        "sensors": SENSORS,
        "scope": "read_only; no fault injection performed by this script",
        "evaluation_note": "Pipeline completion is not factual correctness. Independently review every response.",
        "cases": [],
    }
    for index, (qid, question, sources) in enumerate(QUESTIONS, 1):
        report_file = output_dir / f"{qid.lower()}_planner.json"
        report_file.unlink(missing_ok=True)
        # Explicit scope disambiguates the plural references in compact paper queries.
        scoped_question = (
            question + " Selected reactor measurements: " +
            ", ".join(f"{kind} {s['tag']} ({s['asset']}, {s['signal']})" for kind, s in SENSORS.items()) +
            ". Use only verified source relationships; report missing mappings and evidence. " +
            f"Simulation run: {args.run_id}."
        )
        cmd = [sys.executable, str(planner), "--question", scoped_question,
               "--run-id", args.run_id, "--model", args.model,
               "--output", str(report_file), "--mapping-discovery", args.mapping_discovery,
               "--temporal-coverage", args.temporal_coverage]
        started = time.monotonic()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
            elapsed = round(time.monotonic() - started, 2)
            try:
                planner_report = load_json(report_file)
            except (OSError, json.JSONDecodeError):
                planner_report = None
            status = (planner_report or {}).get("status", "NO_VALID_REPORT")
            error = (planner_report or {}).get("error")
            if result.returncode and not error:
                error = result.stderr[-1500:] or "Planner failed without an error message"
        except subprocess.TimeoutExpired:
            elapsed, status, error = round(time.monotonic() - started, 2), "TIMEOUT", "Planner timed out"
        item = {
            "id": qid, "question": question, "sources_required": sources,
            "planner_status": status, "elapsed_seconds": elapsed,
            "planner_report": str(report_file) if report_file.is_file() else None,
            "reference_answer": references.get(qid),
            "factual_correctness": "NOT_ASSESSED",
            "cross_domain_links_verified": "NOT_ASSESSED",
            "error": error,
        }
        summary["cases"].append(item)
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"{qid}: {status} ({elapsed}s)")
    print(f"Saved {output_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
