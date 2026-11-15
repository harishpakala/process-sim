"""HTTP-facing adapter for the frozen, externally checked-out DTwise bridge.

Only transports a question to the previously benchmarked CLI. No planning,
SPARQL compilation, answer rewriting, or fallback occurs here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


class DtwiseUnavailable(RuntimeError):
    """The configured frozen runtime or its dependencies are unavailable."""


class DtwiseRejected(ValueError):
    """The frozen planner rejected a question."""


def run_question(question: str, *, runner=subprocess.run, environ=None):
    env = os.environ if environ is None else environ
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    question = question.strip()
    dtwise_root = env.get("DTWISE_ROOT")
    schema = env.get("DTWISE_SCHEMA")
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dtwise_root or not schema or not graphdb:
        raise DtwiseUnavailable("Configure DTWISE_ROOT, DTWISE_SCHEMA and GRAPHDB_SPARQL_ENDPOINT")
    root = Path(dtwise_root).expanduser().resolve()
    schema_path = Path(schema).expanduser().resolve()
    bridge = ROOT / "scripts" / "dtwise_bridge.py"
    if not (root / "dtwise" / "semantic_planner.py").is_file():
        raise DtwiseUnavailable("Configured DTWISE_ROOT does not contain the frozen planner")
    if not schema_path.is_file():
        raise DtwiseUnavailable("Configured DTWISE_SCHEMA does not exist")
    if not bridge.is_file():
        raise DtwiseUnavailable("DTwise bridge script is unavailable")
    args = [sys.executable, str(bridge), "--dtwise-root", str(root),
            "--schema", str(schema_path), "--graphdb-url", graphdb,
            "--question", question, "--execute"]
    try:
        completed = runner(args, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise DtwiseUnavailable("DTwise execution timed out") from exc
    except OSError as exc:
        raise DtwiseUnavailable("DTwise process could not start") from exc
    if completed.returncode != 0:
        # Never expose raw tracebacks, environment details, or arbitrary paths.
        raise DtwiseRejected("Frozen DTwise planner/executor rejected the request; check backend logs")
    try:
        result = json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise DtwiseUnavailable("DTwise bridge returned invalid JSON") from exc
    if (not isinstance(result, dict) or result.get("mode") != "frozen_dtwise_graphdb"
            or result.get("executed") is not True
            or not isinstance(result.get("sparql"), str)
            or not isinstance(result.get("answer"), dict)):
        raise DtwiseUnavailable("DTwise bridge returned an unexpected result")
    return result
