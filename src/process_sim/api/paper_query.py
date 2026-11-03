"""Read-only Q1-Q10 paper evaluation bridge for the web UI."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("Evaluation module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def questions():
    q = _load("tep_nexus_paper_queries_web", "scripts/tep_nexus_paper_queries.py")
    return [{"id": f"Q{i}", "question": value, "requiresRun": i >= 8}
            for i, value in enumerate(q.QUESTIONS, 1)]


def answer(question_id, run_id=None, event_id=None):
    if question_id not in {f"Q{i}" for i in range(1, 11)}:
        raise ValueError("Select one of Q1-Q10")
    if event_id and not run_id:
        raise ValueError("A run is required when an event is selected")
    if run_id:
        run_id = str(UUID(run_id))
    if event_id:
        event_id = str(UUID(event_id))
    number = int(question_id[1:])
    if number >= 8 and not run_id:
        raise ValueError("Q8-Q10 require a recorded simulation run")
    evaluation = _load("tep_nexus_paper_evaluation_web", "scripts/tep_nexus_paper_evaluation.py")
    query = _load("tep_nexus_paper_queries_web_answer", "scripts/tep_nexus_paper_queries.py")
    engineering = evaluation.engineering_evidence(
        str(ROOT / "examples/aas/asset_inventory_instance.json"),
        str(ROOT / "examples/aas/product_catalog_instance.json"))
    graph = evaluation.verified_graphdb_mappings(
        os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"))
    temporal = None
    if run_id:
        dsn = os.environ.get("TEP_TIMESCALE_DSN")
        if not dsn:
            raise RuntimeError("TEP_TIMESCALE_DSN is not configured")
        temporal = evaluation.temporal_evidence(
            dsn, run_id, [x[2] for x in evaluation.ASSETS.values()])
        if event_id:
            selected = temporal.get("selected_activation")
            if not selected or selected["event_id"] != event_id:
                raise ValueError("Selected event is not the run's first recorded injection command; this evaluation backend cannot yet rebase samples to another event")
    item = next(x for x in evaluation.evaluate(engineering, temporal, graph)
                if x["id"] == question_id)
    text = query.QUESTIONS[number - 1]
    fallback = query.answer_for(item, engineering, temporal, None)
    response = fallback
    model = os.environ.get("TEP_QUERY_MODEL", "llama3.1:8b")
    if item["status"] == "EVIDENCE_AVAILABLE":
        response = query.ollama_json(
            os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            model, query.ANSWER_SYSTEM_PROMPT,
            {"question": text, "evidence": item.get("evidence")})
        if (not isinstance(response, dict) or set(response) != {"answer", "limitations"}
                or not isinstance(response["answer"], str)
                or not isinstance(response["limitations"], list)
                or any(not isinstance(x, str) for x in response["limitations"])):
            raise ValueError("Invalid Ollama answer format")
    return {
        "id": question_id, "question": text, "status": item["status"],
        "answer": response["answer"], "limitations": response["limitations"],
        "evidence": item.get("evidence"), "reason": item.get("reason"),
        "runId": run_id, "eventId": event_id,
        "model": model if item["status"] == "EVIDENCE_AVAILABLE" else None,
        "promptVersion": query.PROMPT_VERSION,
        "answerValidation": "NOT_AUTOMATICALLY_VERIFIED",
        "warning": "Fault events record operator commands; actual activation and causality are not verified."
    }
