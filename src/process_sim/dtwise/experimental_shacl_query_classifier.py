"""Extract query intent, then map its structure to existing single-domain planners.

Extraction is model-driven; routing is deterministic. Existing operation validators
remain authoritative for schema grounding and supported syntax.
"""
from __future__ import annotations

import json

from process_sim.dtwise.experimental_shacl_ollama import ollama_select

OPERATIONS = (
    "phase1-plan", "phase2-filter", "phase3-and", "phase4-join",
    "phase4-filtered-join", "phase4-and-join", "direct-intent",
)

INTENT_PROMPT = """Extract the semantic query structure, NOT an operation name.
Return only JSON with EXACTLY these fields:
{
  "action": "retrieve" or "aggregate" or "other",
  "results": ["owner.property", ...],
  "shared_owner": string or null,
  "filters": [{"property": "owner.property", "operator": "=", "value": "literal"}, ...],
  "boolean_operator": "AND" or "OR" or "MIXED" or null,
  "explicit_filter_syntax": boolean
}
Results must list separately requested result properties, not intermediate
SHACL traversal nodes. A path like Device -> EndPoint -> Address has ONE result,
not a sibling join. shared_owner is non-null ONLY when multiple result branches
are explicitly requested to share the same owner. It is NOT a traversal parent.
Extract filters expressed in natural language (e.g. 'with LocalId FI_101')
as well as filters written with '='. Set explicit_filter_syntax true only when
filters are written using explicit equality signs (=) in the question.
Extract all constraints even if the query may be unsupported. For AND/OR mixes
use MIXED. For simple retrieval without conditions use an empty filters list.
Do not invent schema properties, paths, filter values or a shared owner.
Do not classify into planner operations. No prose outside JSON."""


def validate_intent(raw: str) -> dict:
    try:
        intent = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid structured-intent JSON") from exc
    required = {"action", "results", "shared_owner", "filters",
                "boolean_operator", "explicit_filter_syntax"}
    if not isinstance(intent, dict) or set(intent) != required:
        raise ValueError("Invalid structured-intent fields")
    if intent["action"] not in ("retrieve", "aggregate", "other"):
        raise ValueError("Invalid intent action")
    if not isinstance(intent["results"], list) or not all(
            isinstance(x, str) and x.strip() for x in intent["results"]):
        raise ValueError("Invalid intent results")
    if intent["shared_owner"] is not None and (not isinstance(intent["shared_owner"], str)
            or not intent["shared_owner"].strip()):
        raise ValueError("Invalid shared owner")
    if intent["boolean_operator"] not in (None, "AND", "OR", "MIXED"):
        raise ValueError("Invalid Boolean operator")
    if not isinstance(intent["explicit_filter_syntax"], bool):
        raise ValueError("Invalid explicit-filter-syntax flag")
    if not isinstance(intent["filters"], list) or not all(
            isinstance(f, dict) and set(f) == {"property", "operator", "value"}
            and isinstance(f["property"], str) and f["property"].strip()
            and isinstance(f["operator"], str)
            and isinstance(f["value"], str) and f["value"].strip()
            for f in intent["filters"]):
        raise ValueError("Invalid intent filters")
    return intent


def operation_from_intent(intent: dict) -> dict:
    """Pure structural routing. A selected operation may still abstain."""
    intent = validate_intent(json.dumps(intent))
    filters = intent["filters"]
    count = len(filters)
    sibling = len(intent["results"]) > 1 and intent["shared_owner"] is not None
    reason = "Mapped extracted query structure; operation validation remains authoritative"
    unsupported = {"status": "unsupported", "operation": None,
                   "reason": "Query structure has no supported single-domain operation"}
    if intent["action"] != "retrieve" or not intent["results"]:
        return unsupported
    if any(f["operator"] != "=" for f in filters):
        return unsupported
    if count > 1 and intent["boolean_operator"] is None:
        return unsupported
    if count <= 1 and intent["boolean_operator"] is not None:
        return unsupported
    if sibling:
        if count == 0:
            operation = "phase4-join"
        elif count == 1:
            operation = "phase4-filtered-join" if intent["explicit_filter_syntax"] else "direct-intent"
        else:
            operation = "phase4-and-join" if intent["explicit_filter_syntax"] else "direct-intent"
    elif count == 0:
        operation = "phase1-plan"
    elif count == 1:
        operation = "phase2-filter"
    elif count == 2 and intent["boolean_operator"] == "AND":
        operation = "phase3-and"
    else:
        return unsupported
    return {"status": "supported", "operation": operation, "reason": reason}


def classify_single_domain_query(question: str, *, model="qwen2.5-coder:7b",
                                 endpoint="http://127.0.0.1:11434", transport=None) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty")
    raw = ollama_select({"question": question}, model=model, endpoint=endpoint,
                        transport=transport, system_prompt=INTENT_PROMPT)
    intent = validate_intent(raw)
    return {**operation_from_intent(intent), "intent": intent}
