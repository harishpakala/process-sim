"""LLM-first compositional semantic selection over a verified evidence catalog."""
from __future__ import annotations

import json
import time

from .semantic_planning import build_evidence_catalog, validate_semantic_plan


SYSTEM_PROMPT = (
    "Translate the user question into a compositional semantic query using "
    "ONLY the supplied evidence IDs. Return a JSON object with exactly "
    "version, scope, operation, projections, where. version='2.0'. "
    "scope is a nonempty list of entity IDs; operation is select_entities, "
    "select_values, or count. projections is a list of property IDs (only "
    "for select_values). where is null or a Boolean expression tree. "
    "Boolean nodes: {'operator':'and'|'or','conditions':[...]} with at "
    "least two children; {'operator':'not','condition':...}. "
    "Leaf nodes: {'operator':'exists'|'not_exists','property_id':'P...'} "
    "or {'operator':'eq'|'neq'|'contains'|'regex','property_id':'P...',"
    "'value':literal}. Property IDs must belong to a selected entity. "
    "Return entity-presence queries as select_entities with empty projections. "
    "Use AND when all conditions must hold, OR when any may hold, "
    "not_exists for missing properties. Do not generate SPARQL or invent IDs."
)


def select_semantic_plan(question, catalog, *, model, request_json, ollama_host,
                         timeout, keep_alive=None, prompt_diagnostics=None,
                         max_attempts=2):
    """Ask the LLM for an IR; validate IDs and structure, then retry with feedback.

    No deterministic operation choice or fallback: invalid responses are
    returned to the model for correction, and the final failure is raised.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be nonempty")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("Invalid selection attempt count")
    evidence = build_evidence_catalog(catalog)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "question": question, "evidence": evidence.as_prompt()
        }, ensure_ascii=False, separators=(",", ":"))},
    ]
    history = []
    for attempt in range(max_attempts):
        payload = {
            "model": model, "stream": False, "format": "json",
            "options": {"temperature": 0}, "messages": messages,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        started = time.perf_counter()
        raw = "{}"
        try:
            response = request_json(
                ollama_host.rstrip("/") + "/api/chat", payload, timeout)
            raw = response["message"]["content"]
            selected = json.loads(raw)
            validated = validate_semantic_plan(selected, evidence)
        except (KeyError, TypeError, ValueError) as exc:
            reason = str(exc)
            history.append({"attempt": attempt + 1, "error": reason})
            if prompt_diagnostics is not None:
                prompt_diagnostics.update({
                    "stage": "semantic_selection_v2", "attempts": history,
                    "request_status": "retrying" if attempt + 1 < max_attempts else "failed",
                })
                from .experimental_evidence_selection import _write_prompt_diagnostics
                _write_prompt_diagnostics(prompt_diagnostics)
            if attempt + 1 == max_attempts:
                raise ValueError("Semantic selection failed validation: " + reason) from exc
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                 "The previous JSON was rejected: " + reason +
                 ". Correct the selection using ONLY the supplied evidence IDs "
                 "and the original question. Return the complete corrected JSON."},
            ]
            continue
        history.append({"attempt": attempt + 1, "seconds": round(
            time.perf_counter() - started, 3), "status": "validated"})
        if prompt_diagnostics is not None:
            prompt_diagnostics.update({
                "stage": "semantic_selection_v2", "attempts": history,
                "request_status": "completed", "selection": validated,
            })
            from .experimental_evidence_selection import _write_prompt_diagnostics
            _write_prompt_diagnostics(prompt_diagnostics)
        return validated, evidence
    raise AssertionError("Unreachable selection state")
