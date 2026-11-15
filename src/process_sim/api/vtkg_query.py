"""HTTP adapter for the existing constrained TEP NEXUS VTKG CLI.

No new planner, mapping inference, SQL, or RDF materialization.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]


class VtkgUnavailable(RuntimeError):
    pass


def run_question(payload: dict, *, runner=subprocess.run, environ=None):
    env = os.environ if environ is None else environ
    if not isinstance(payload, dict) or set(payload) != {
        "question", "engineering_function", "run_id",
        "start_simulation_seconds", "end_simulation_seconds", "limit"
    }:
        raise ValueError("VTKG requires question, engineering_function, run_id, start_simulation_seconds, end_simulation_seconds and limit")
    question = payload["question"]
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    # Use the already-tested validator; no heuristic parsing of time/function.
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from tep_nexus_live_virtual_graph import validate_request
        req = validate_request(payload["engineering_function"], payload["run_id"],
                               payload["start_simulation_seconds"],
                               payload["end_simulation_seconds"], payload["limit"])
    finally:
        sys.path.remove(str(scripts))
    dsn = env.get("TEP_TIMESCALE_DSN")
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dsn or not graphdb:
        raise VtkgUnavailable("Configure TEP_TIMESCALE_DSN and GRAPHDB_SPARQL_ENDPOINT")
    cli = scripts / "tep_nexus_unified_virtual_query.py"
    if not cli.is_file():
        raise VtkgUnavailable("Existing VTKG query CLI is unavailable")
    with tempfile.TemporaryDirectory(prefix="tep-vtkg-") as tmp:
        output = Path(tmp) / "result.json"
        args = [sys.executable, str(cli), "--question", question.strip(),
                "--function", req["engineering_function"], "--run-id", req["run_id"],
                "--start-seconds", str(req["start_simulation_seconds"]),
                "--end-seconds", str(req["end_simulation_seconds"]),
                "--limit", str(req["limit"]), "--graphdb-url", graphdb,
                "--output", str(output)]
        try:
            completed = runner(args, cwd=str(ROOT), env=dict(env),
                               capture_output=True, text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VtkgUnavailable("VTKG query process failed or timed out") from exc
        if completed.returncode != 0:
            logging.error("VTKG CLI exited %s; stderr: %s", completed.returncode,
                          (completed.stderr or "")[-6000:])
            raise VtkgUnavailable("VTKG query rejected or failed; inspect backend logs")
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VtkgUnavailable("VTKG CLI returned no valid report") from exc
    if (not isinstance(report, dict) or report.get("materializedInGraphDB") is not False
            or not isinstance(report.get("evidence"), dict)
            or not isinstance(report["evidence"].get("observations"), list)
            or not isinstance(report.get("validatedPlan"), dict)):
        raise VtkgUnavailable("VTKG CLI returned unexpected evidence")
    return report
