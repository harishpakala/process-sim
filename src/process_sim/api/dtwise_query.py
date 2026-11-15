
"""HTTP-facing adapter for the repository-local DTWise integration.

Transports natural-language questions to the Process-Sim DTWise bridge.
Planning, SPARQL compilation and GraphDB execution happen in the bridge.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


class DtwiseUnavailable(RuntimeError):
    """DTWise runtime, configuration, or dependencies are unavailable."""


class DtwiseRejected(ValueError):
    """DTWise rejected the question or execution failed."""


def run_question(question: str, *, runner=subprocess.run, environ=None):
    env = os.environ if environ is None else environ

    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")

    question = question.strip()

    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")

    if not graphdb:
        raise DtwiseUnavailable(
            "Configure GRAPHDB_SPARQL_ENDPOINT"
        )

    bridge = ROOT / "scripts" / "dtwise_bridge.py"
    local_dtwise = ROOT / "src" / "process_sim" / "dtwise"

    if not (local_dtwise / "semantic_planner.py").is_file():
        raise DtwiseUnavailable(
            "Repository-local DTWise semantic planner is unavailable"
        )

    if not bridge.is_file():
        raise DtwiseUnavailable("DTWise bridge script is unavailable")

    args = [
        sys.executable,
        str(bridge),
        "--graphdb-url", graphdb,
        "--question", question,
        "--execute",
    ]

    process_env = dict(env)
    src_path = str(ROOT / "src")
    existing_path = process_env.get("PYTHONPATH", "")
    process_env["PYTHONPATH"] = os.pathsep.join(
        p for p in (src_path, existing_path) if p
    )

    try:
        completed = runner(
            args,
            cwd=str(ROOT),
            env=process_env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DtwiseUnavailable("DTWise execution timed out") from exc
    except OSError as exc:
        raise DtwiseUnavailable(
            "DTWise process could not start"
        ) from exc

    if completed.returncode != 0:
        logging.error(
            "DTWise bridge exited %s; stderr: %s",
            completed.returncode,
            (completed.stderr or "")[-6000:],
        )
        raise DtwiseRejected(
            "DTWise bridge failed; inspect backend stderr for details"
        )

    try:
        result = json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise DtwiseUnavailable(
            "DTWise bridge returned invalid JSON"
        ) from exc

    if (
        not isinstance(result, dict)
        or result.get("mode") != "frozen_dtwise_graphdb"
        or result.get("executed") is not True
        or not isinstance(result.get("sparql"), str)
        or not isinstance(result.get("answer"), dict)
    ):
        raise DtwiseUnavailable(
            "DTWise bridge returned an unexpected result"
        )

    return result
