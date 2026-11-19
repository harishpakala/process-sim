"""LLM-first compositional semantic selection over a verified evidence catalog."""
from __future__ import annotations

import json
import time
from urllib.error import URLError

from .semantic_planning import build_evidence_catalog, validate_semantic_plan
from .evidence_retrieval import retrieve_evidence


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
    "Use select_entities when the user asks WHICH entities match conditions; "
    "set projections=[] even if property names appear in the conditions. "
    "Use select_values ONLY when the user explicitly requests property values "
    "to be returned, such as listing addresses or identifiers. "
    "Use count ONLY for a requested numeric count. "
    "Scope contains shapes to search, not shapes to join. "
    "Never assume that multiple shapes imply a relationship or that "
    "SHACL shape membership follows from sharing property predicates. "
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
    full_evidence = build_evidence_catalog(catalog)
    evidence = retrieve_evidence(question, full_evidence,
                                 max_entities=8, max_properties=32,
                                 max_relationships=16)
    # Send compact IDs and labels, not long shape/predicate IRIs. Validation
    # and compilation still use the full authoritative evidence records.
    prompt_evidence = {
        "entities": [{"id": e["id"], "domain": e["domain"],
                      "label": e["shape"].rsplit("/", 1)[-1]}
                     for e in evidence.entities],
        "properties": [{"id": p["id"], "entity_id": p["entity_id"],
                        "label": p["label"]} for p in evidence.properties],
        "relationships": [{"id": r["id"],
                           "from_entity_id": r["from_entity_id"],
                           "to_entity_id": r["to_entity_id"],
                           "label": r["predicate"].rsplit("/", 1)[-1]}
                          for r in evidence.relationships],
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "question": question, "evidence": prompt_evidence
        }, ensure_ascii=False, separators=(",", ":"))},
    ]
    history = []
    if prompt_diagnostics is not None:
        prompt_diagnostics.update({
            "stage": "semantic_selection_v2",
            "request_status": "prepared",
            "candidate_counts": {
                "entities": len(evidence.entities),
                "properties": len(evidence.properties),
                "relationships": len(evidence.relationships),
            },
            "prompt_characters": sum(len(m["content"]) for m in messages),
        })
        from .experimental_evidence_selection import _write_prompt_diagnostics
        _write_prompt_diagnostics(prompt_diagnostics)
    for attempt in range(max_attempts):
        payload = {
            "model": model, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 384},
            "messages": messages,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        started = time.perf_counter()
        if prompt_diagnostics is not None:
            prompt_diagnostics.update({"request_status": "waiting_for_ollama",
                                       "current_attempt": attempt + 1})
            _write_prompt_diagnostics(prompt_diagnostics)
        raw = "{}"
        try:
            response = request_json(
                ollama_host.rstrip("/") + "/api/chat", payload, timeout)
            raw = response["message"]["content"]
            selected = json.loads(raw)
            validated = validate_semantic_plan(selected, evidence)
            # Also check against the complete authoritative SHACL catalog.
            validate_semantic_plan(validated, full_evidence)
        except (TimeoutError, OSError, URLError) as exc:
            if prompt_diagnostics is not None:
                prompt_diagnostics.update({"request_status": "transport_failed",
                                           "elapsed_seconds": round(time.perf_counter() - started, 3),
                                           "error": str(exc)})
                _write_prompt_diagnostics(prompt_diagnostics)
            raise
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
