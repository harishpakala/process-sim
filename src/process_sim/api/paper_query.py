"""Read-only Q1-Q10 paper evaluation bridge for the web UI."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import UUID

from process_sim.api.catalog_grounding import POLICY, flags as grounding_flags

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
    display = list(q.QUESTIONS)
    display[7] = "Which fault injection command was recorded, and when? Was activation verified?"
    display[8] = "What were XMEAS6–XMEAS9 measurements immediately before and after the selected fault command?"
    display[9] = "What are FI-1101's engineering references and XMEAS6 measurements around the selected command?"
    return [{"id": f"Q{i}", "question": value, "requiresRun": i >= 8}
            for i, value in enumerate(display, 1)]


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
    graph = (evaluation.verified_graphdb_mappings(
        os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"))
        if number in {1, 2, 3, 6, 7, 10} else None)
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
    if number == 8:
        text = "Which fault injection operator command was recorded, and at what simulation time? Is actual activation verified?"
    elif number == 9:
        text = ("For XMEAS6, XMEAS7, XMEAS8 and XMEAS9, report the recorded values and "
                "simulation timestamps immediately before and after the selected injection command.")
    elif number == 10:
        text = ("For FI-1101, report the AAS AssetIdentifier, DEXPI and ECAD references, "
                "product candidate, ECLASS class and signal, together with recorded XMEAS6 "
                "measurements immediately before and after the selected injection command.")

    fallback = query.answer_for(item, engineering, temporal, None)
    response = fallback
    model = os.environ.get("TEP_QUERY_MODEL", "llama3.1:8b")
    if item["status"] == "EVIDENCE_AVAILABLE":
        response = query.ollama_json(
            os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            model, query.ANSWER_SYSTEM_PROMPT + POLICY,
            {"question": text, "evidence": item.get("evidence")})
        if (not isinstance(response, dict) or set(response) != {"answer", "limitations"}
                or not isinstance(response["answer"], str)
                or not isinstance(response["limitations"], list)
                or any(not isinstance(x, str) for x in response["limitations"])):
            raise ValueError("Invalid Ollama answer format")
    checks = grounding_flags(response["answer"], response["limitations"], item.get("evidence") or {}, question_id)
    if checks:
        response = fallback
    return {
        "id": question_id, "question": text, "status": item["status"],
        "questionAdaptation": "UI_CONTEXTUAL_TEMPORAL_WORDING" if number >= 8 else "PAPER_SCRIPT_DEFAULT",
        "answer": response["answer"], "limitations": response["limitations"],
        "evidence": item.get("evidence"), "reason": item.get("reason"),
        "runId": run_id, "eventId": event_id,
        "model": model if item["status"] == "EVIDENCE_AVAILABLE" else None,
        "promptVersion": query.PROMPT_VERSION,
        "answerValidation": "REJECTED_MODEL_ANSWER_USED_EVIDENCE_FALLBACK" if checks else "HEURISTIC_CHECKS_PASSED_NOT_VERIFIED",
        "validationFlags": checks,
        "warning": "Fault events record operator commands; actual activation and causality are not verified."
    }


def custom_answer(question, run_id=None, event_id=None):
    """Exploratory queries: route to a supported read-only evidence scope, never execute LLM code."""
    import re
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    question = question.strip()
    if run_id:
        run_id = str(UUID(run_id))
    if event_id:
        event_id = str(UUID(event_id))
    if event_id and not run_id:
        raise ValueError("Select a run for the recorded event")

    q = question.lower()
    temporal_words = ("fault", "inject", "before", "after", "historian",
                      "recorded value", "measurement", "timeseries", "time series",
                      "simulation time", "operational history", "trend")
    product_words = ("product", "manufacturer", "catalog", "vendor", "model", "qudt",
                     "eclass", "irdi", "specification", "accuracy", "range")
    engineering_words = ("instrument", "reactor", "signal", "asset", "tag", "ecad",
                         "dexpi", "mapping", "identifier", "reference", "pi-1101",
                         "fi-1101", "ti-1101", "li-1101", "electrical", "engineering")
    needs_temporal = any(word in q for word in temporal_words)
    needs_products = any(word in q for word in product_words)
    needs_engineering = any(word in q for word in engineering_words) or needs_products
    if not (needs_temporal or needs_engineering):
        raise ValueError("This exploratory interface currently supports engineering assets, product specifications, and recorded fault/signal evidence only.")
    if needs_temporal and not run_id:
        raise ValueError("This question requires recorded operational evidence. Select a simulation run first.")

    evaluation = _load("tep_nexus_custom_evaluation", "scripts/tep_nexus_paper_evaluation.py")
    query = _load("tep_nexus_custom_queries", "scripts/tep_nexus_paper_queries.py")
    engineering = evaluation.engineering_evidence(
        str(ROOT / "examples/aas/asset_inventory_instance.json"),
        str(ROOT / "examples/aas/product_catalog_instance.json"))
    graph = None
    if needs_engineering:
        graph = evaluation.verified_graphdb_mappings(
            os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"))
    temporal = None
    if needs_temporal:
        dsn = os.environ.get("TEP_TIMESCALE_DSN")
        if not dsn:
            raise RuntimeError("TEP_TIMESCALE_DSN is not configured")
        temporal = evaluation.temporal_evidence(
            dsn, run_id, [x[2] for x in evaluation.ASSETS.values()])
        selected = temporal.get("selected_activation")
        if event_id and (not selected or selected["event_id"] != event_id):
            raise ValueError("The selected event is not the first recorded injection command; event-specific sampling is not yet supported.")
        if not selected:
            raise ValueError("No recorded injection command is available in the selected run.")

    evidence = {}
    if graph is not None:
        evidence["graphdb_verified_mappings"] = list(graph.values())
    if needs_products:
        evidence["engineering_catalog"] = engineering
    if temporal is not None:
        evidence["activation"] = temporal.get("selected_activation")
        evidence["measurements"] = temporal.get("measurements", {})
        evidence["run_id"] = run_id
    model = os.environ.get("TEP_QUERY_MODEL", "llama3.1:8b")
    response = query.ollama_json(
        os.environ.get("OLLAMA_URL", "http://localhost:11434"), model,
        query.ANSWER_SYSTEM_PROMPT + POLICY + """
Exploratory query mode: do not claim evidence for facts not present in the supplied fields.
If the question is outside the retrieved evidence scope, explain that limitation.
Do not interpret an operator command as verified fault activation.
""", {"question": question, "evidence": evidence})
    if (not isinstance(response, dict) or set(response) != {"answer", "limitations"}
            or not isinstance(response["answer"], str)
            or not isinstance(response["limitations"], list)
            or any(not isinstance(v, str) for v in response["limitations"])):
        raise ValueError("Invalid Ollama response format")
    checks = grounding_flags(response["answer"], response["limitations"], evidence)
    if checks:
        response = {"answer": "The generated response failed ProductCatalog evidence checks. Please review the retrieved evidence.",
                    "limitations": ["Grounding validation flags: " + ", ".join(checks)]}
    return {
        "id": "CUSTOM", "question": question, "answer": response["answer"],
        "limitations": response["limitations"], "status": "EVIDENCE_AVAILABLE",
        "evidence": evidence, "runId": run_id if needs_temporal else None,
        "eventId": event_id if needs_temporal else None,
        "model": model, "promptVersion": "EXPLORATORY_V1_NOT_PAPER_BASELINE",
        "answerValidation": "REJECTED_MODEL_ANSWER" if checks else "HEURISTIC_CHECKS_PASSED_NOT_VERIFIED",
        "validationFlags": checks,
        "warning": "Fault events record operator commands; activation and causality are not verified.",
        "questionAdaptation": "EXPLORATORY_NOT_PAPER_EVALUATION"
    }
