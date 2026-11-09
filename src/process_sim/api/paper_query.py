"""Read-only Q1-Q12 paper question bridge for the web UI."""

# Created: 2026-11-03
# Author: Harish
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from uuid import UUID

from process_sim.api.catalog_grounding import POLICY, flags as grounding_flags, catalog_records

ROOT = Path(__file__).resolve().parents[3]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("Evaluation module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _independent_questions():
    path = ROOT / "reports/independent_questions_v2.json"
    entries = json.loads(path.read_text(encoding="utf-8-sig"))["questions"]
    if [entry["id"] for entry in entries] != [f"Q{i}" for i in range(1, 11)]:
        raise ValueError("Invalid independent question registry")
    result = {entry["id"]: entry["question"] for entry in entries}
    result["Q11"] = "What ECLASS IRDI is associated with the product candidate linked to reactor temperature instrument TI-1101?"
    result["Q12"] = "What temperature-signal observations were recorded for reactor temperature instrument TI-1101 (XMEAS9) between simulation time 0 and 60 seconds in the selected simulation run?"
    return result


def questions():
    return [{"id": key, "question": value, "requiresRun": int(key[1:]) >= 8}
            for key, value in _independent_questions().items()]


UI_V4_1_RULES = """
For Q3, pair each canonical AAS AssetIdentifier with its operational signal.
For Q4, pair each equipment tag with its ProductCatalog product candidate and manufacturer.
For Q6, give DEXPI, ECAD, AAS AssetIdentifier and product-candidate relationships,
without ECLASS classification claims.
When catalog evidence is present, never claim it was not retrieved.
"""


def _ui_completeness_flags(question_id, answer_text, evidence):
    import re
    def paired(left, right):
        return any(left in clause and right in clause
                   for clause in re.split(r"[;\n]", answer_text))
    issues = []
    mappings = evidence.get("graphdb_verified_mappings", [])
    if question_id == "Q3":
        for mapping in mappings:
            if mapping.get("assetId") and mapping.get("signal") and not paired(mapping["assetId"], mapping["signal"]):
                issues.append("MISSING_ASSET_SIGNAL_PAIR:" + mapping["assetId"])
    if question_id == "Q4":
        for record in catalog_records(evidence):
            tag, product = record.get("equipment_tag"), record.get("product_key")
            if tag and product and not paired(tag, product):
                issues.append("MISSING_TAG_PRODUCT_PAIR:" + tag)
    if question_id == "Q6":
        for mapping in mappings:
            for field in ("assetId", "dexpiLocal", "ecadLocal", "productId"):
                value = mapping.get(field)
                if value and value not in answer_text and (
                        field != "productId" or value.rsplit("/", 1)[-1] not in answer_text):
                    issues.append("MISSING_MAPPING_FIELD:" + field + ":" + value)
    if question_id in ("Q7", "Q10"):
        records = catalog_records(evidence)
        for mapping in mappings:
            record = next((r for r in records if r.get("product_uri") == mapping.get("productId")), None)
            if record is None:
                issues.append("MISSING_PRODUCTCATALOG_JOIN")
            elif record.get("eclass_class") and record["eclass_class"] not in answer_text:
                issues.append("MISSING_PRODUCTCATALOG_CLASS")
    return issues


def _answer_q11_q12(question_id, run_id):
    """UI-only live evidence path; distinct from the frozen 12-question assessment."""
    evaluation = _load("tep_nexus_paper_evaluation_web_extended", "scripts/tep_nexus_paper_evaluation.py")
    engineering = evaluation.engineering_evidence(
        str(ROOT / "examples/aas/asset_inventory_instance.json"),
        str(ROOT / "examples/aas/product_catalog_instance.json"))
    temperature = engineering["temperature"]
    if temperature.get("equipment_tag") != "TI-1101" or temperature.get("signal") != "XMEAS9":
        raise ValueError("Temperature instrument mapping does not match the supported fixture")
    evidence = {}
    if question_id == "Q11":
        evidence = {"engineering_catalog": {"temperature": temperature}}
        irdi = temperature.get("eclass_irdi")
        status = "EVIDENCE_AVAILABLE" if irdi else "NO_EVIDENCE"
        response = (f"TI-1101 is associated with product candidate {temperature.get('product_key')}; "
                    f"its recorded ECLASS IRDI is {irdi}. This is not physical installation verification.") if irdi else "No ECLASS IRDI is recorded for the TI-1101 product candidate."
    else:
        dsn = os.environ.get("TEP_TIMESCALE_DSN")
        if not dsn:
            raise RuntimeError("TEP_TIMESCALE_DSN is not configured")
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                samples = conn.execute("""
                    SELECT simulation_time_hours, value, observed_at
                    FROM public.signal_samples
                    WHERE run_id = %s::uuid AND signal_id = %s
                      AND simulation_time_hours >= %s AND simulation_time_hours <= %s
                    ORDER BY simulation_time_hours, observed_at
                    LIMIT %s
                """, (run_id, "XMEAS9", 0.0, 60.0 / 3600.0, 5001)).fetchall()
        observations = [{"simulation_seconds": float(t) * 3600, "value": float(v),
                         "observed_at": ts.isoformat()}
                        for t, v, ts in samples[:5000]]
        evidence = {"signal": "XMEAS9", "equipment_tag": "TI-1101", "run_id": run_id,
                    "interval_seconds_inclusive": [0, 60],
                    "truncated": len(samples) > 5000, "observations": observations}
        status = "EVIDENCE_AVAILABLE" if observations else "NO_EVIDENCE"
        response = (f"Retrieved {len(observations)} recorded XMEAS9 observations for TI-1101 "
                    f"between 0 and 60 simulation seconds; see the evidence table for every "
                    f"timestamp and raw value.{' The result is truncated.' if evidence['truncated'] else ''}"
                    if observations else "No XMEAS9 observations were recorded in the selected interval.")
    return {"id": question_id, "question": _independent_questions()[question_id],
            "status": status, "answer": response,
            "limitations": ["Product association does not verify physical installation."] if question_id == "Q11" else
                           ["Raw historian values do not independently establish measurement units or instrument state."],
            "evidence": evidence, "reason": None if status == "EVIDENCE_AVAILABLE" else "No matching evidence",
            "runId": run_id, "eventId": None, "model": None,
            "promptVersion": "Q11_Q12_UI_EVIDENCE_ONLY",
            "questionAdaptation": "LIVE_UI_NOT_FROZEN_12_QUESTION_REPLAY",
            "answerValidation": "DETERMINISTIC_EVIDENCE_SUMMARY_NOT_LLM",
            "validationFlags": [], "displayedAnswerValidationFlags": [],
            "answerSource": "DETERMINISTIC_EVIDENCE_FALLBACK",
            "warning": "No fault activation or physical sensor state is inferred."}


def answer(question_id, run_id=None, event_id=None):
    if question_id not in {f"Q{i}" for i in range(1, 13)}:
        raise ValueError("Select one of Q1-Q12")
    if event_id and not run_id:
        raise ValueError("A run is required when an event is selected")
    if run_id:
        run_id = str(UUID(run_id))
    if event_id:
        event_id = str(UUID(event_id))
    number = int(question_id[1:])
    if number >= 8 and number != 11 and not run_id:
        raise ValueError("Q8-Q10 and Q12 require a recorded simulation run")
    if number in {11, 12}:
        if event_id:
            raise ValueError("Q11 and Q12 do not use a fault event")
        return _answer_q11_q12(question_id, run_id)
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
    # ProductCatalog is the sole classification authority. Join by exact
    # product URI and never forward GraphDB eclassCode as catalog evidence.
    if number in {7, 10} and item.get("evidence"):
        scoped = item["evidence"]
        mappings = scoped.get("graphdb_verified_mappings", [])
        products = {m.get("productId") for m in mappings}
        matches = {key: record for key, record in engineering.items()
                   if isinstance(record, dict) and record.get("product_uri") in products}
        if products and not matches:
            raise ValueError("ProductCatalog record unavailable for requested product")
        scoped["engineering_catalog"] = matches
    if number == 6 and item.get("evidence"):
        for mapping in item["evidence"].get("graphdb_verified_mappings", []):
            mapping.pop("eclassCode", None)
    text = _independent_questions()[question_id]

    fallback = query.answer_for(item, engineering, temporal, None)
    response = fallback
    model = os.environ.get("TEP_QUERY_MODEL", "llama3.1:8b")
    if item["status"] == "EVIDENCE_AVAILABLE":
        response = query.ollama_json(
            os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            model, query.ANSWER_SYSTEM_PROMPT + POLICY + UI_V4_1_RULES,
            {"question": text, "evidence": item.get("evidence")})
        if (not isinstance(response, dict) or set(response) != {"answer", "limitations"}
                or not isinstance(response["answer"], str)
                or not isinstance(response["limitations"], list)
                or any(not isinstance(x, str) for x in response["limitations"])):
            raise ValueError("Invalid Ollama answer format")
    checks = grounding_flags(response["answer"], response["limitations"], item.get("evidence") or {}, question_id)
    checks = sorted(set(checks + _ui_completeness_flags(question_id, response["answer"], item.get("evidence") or {})))
    displayed_checks = checks
    if checks:
        response = fallback
        displayed_checks = sorted(set(
            grounding_flags(response["answer"], response["limitations"], item.get("evidence") or {}, question_id)
            + _ui_completeness_flags(question_id, response["answer"], item.get("evidence") or {})
        ))
    return {
        "id": question_id, "question": text, "status": item["status"],
        "questionAdaptation": "INDEPENDENT_V4_1_UI_QUESTION_REGISTRY",
        "answer": response["answer"], "limitations": response["limitations"],
        "evidence": item.get("evidence"), "reason": item.get("reason"),
        "runId": run_id, "eventId": event_id,
        "model": model if item["status"] == "EVIDENCE_AVAILABLE" else None,
        "promptVersion": "INDEPENDENT_V4_1_WEB_UI",
        "answerValidation": "REJECTED_MODEL_ANSWER_USED_EVIDENCE_FALLBACK" if checks else "HEURISTIC_CHECKS_PASSED_NOT_VERIFIED",
        "validationFlags": checks,
        "validationFlagsScope": "REJECTED_MODEL_ANSWER" if checks else "DISPLAYED_MODEL_ANSWER",
        "displayedAnswerValidationFlags": displayed_checks,
        "answerSource": "DETERMINISTIC_EVIDENCE_FALLBACK" if checks or item["status"] != "EVIDENCE_AVAILABLE" else "OLLAMA_HEURISTIC_CHECKS_PASSED",
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
        evidence["graphdb_verified_mappings"] = [{k: v for k, v in record.items() if k != "eclassCode"} for record in graph.values()]
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
        "answerSource": "REJECTED_MODEL_ANSWER" if checks else "OLLAMA_HEURISTIC_CHECKS_PASSED",
        "warning": "Fault events record operator commands; activation and causality are not verified.",
        "questionAdaptation": "EXPLORATORY_NOT_PAPER_EVALUATION"
    }
