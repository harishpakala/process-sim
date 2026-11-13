"""Opt-in, single-flight Q13 ontology-guided job runner.

Runs the existing research script in a subprocess, not in the HTTP handler.
Only the server controls the command; callers cannot provide executable code,
paths, GraphDB queries, or arbitrary model arguments.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "scripts" / "run_q13_ontology_guided_v9.py"
_LOCK = threading.Lock()
_JOB: dict = {"state": "IDLE"}
_MAX_SECONDS = 1800


def status() -> dict:
    with _LOCK:
        return dict(_JOB)


def start() -> dict:
    if os.getenv("TEP_Q13_LIVE_ENABLED") != "1":
        raise PermissionError("Live Q13 is disabled; set TEP_Q13_LIVE_ENABLED=1")
    if not os.getenv("TEP_TIMESCALE_DSN"):
        raise ValueError("TEP_TIMESCALE_DSN is required for live Q13")
    if not _SCRIPT.is_file():
        raise FileNotFoundError("Q13 runner script is missing")
    with _LOCK:
        if _JOB.get("state") in ("RUNNING", "QUEUED"):
            raise RuntimeError("A Q13 job is already running")
        job_id = uuid4().hex
        _JOB.clear()
        _JOB.update({"id": job_id, "state": "QUEUED", "startedAt": time.time()})
    threading.Thread(target=_execute, args=(job_id,), daemon=True, name="q13-ontology-job").start()
    return status()


def _execute(job_id: str) -> None:
    output = _ROOT / "reports" / "q13_live" / (job_id + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(_SCRIPT), "--skip-lifting",
        "--graphdb-timeout", "60", "--ollama-timeout", "180",
        "--max-hops", "2", "--output", str(output),
    ]
    with _LOCK:
        _JOB["state"] = "RUNNING"
    try:
        completed = subprocess.run(
            command, cwd=str(_ROOT), env=os.environ.copy(),
            capture_output=True, text=True, timeout=_MAX_SECONDS,
        )
        audit = None
        if output.is_file() and output.stat().st_size <= 8_000_000:
            audit = json.loads(output.read_text(encoding="utf-8"))
        with _LOCK:
            _JOB.update({
                "state": "COMPLETED" if completed.returncode == 0 and
                         isinstance(audit, dict) and audit.get("final_answer") else "FAILED",
                "auditStatus": audit.get("status") if isinstance(audit, dict) else None,
                "synthesisMode": audit.get("synthesis_mode") if isinstance(audit, dict) else None,
                "exitCode": completed.returncode,
                "error": completed.stderr[-1200:] if completed.returncode else None,
                "finishedAt": time.time(),
            })
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        with _LOCK:
            _JOB.update({"state": "FAILED", "error": str(exc)[:1200], "finishedAt": time.time()})


def result() -> dict:
    job = status()
    if job.get("state") != "COMPLETED":
        raise LookupError("No completed live Q13 job")
    path = _ROOT / "reports" / "q13_live" / (job["id"] + ".json")
    audit = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(audit, dict) or not audit.get("final_answer"):
        raise ValueError("Completed audit is invalid")
    return {
        "question": audit.get("question"), "answer": audit["final_answer"],
        "status": audit.get("status"), "method": audit.get("method"),
        "synthesisMode": audit.get("synthesis_mode"),
        "fallbackReason": audit.get("fallback_reason"),
        "acceptance": audit.get("acceptance"), "historian": audit.get("historian"),
        "domains": [{
            "domain": d.get("domain"), "status": d.get("status"),
            "summarySource": (d.get("finding") or {}).get("summary_source"),
            "verifiedTriples": d.get("verified_triples", []),
            "finding": d.get("finding"),
        } for d in audit.get("domains", [])],
    }
