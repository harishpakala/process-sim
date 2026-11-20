"""Strict single-domain query-category selection; never generates SPARQL."""
from __future__ import annotations

import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select

OPERATIONS = (
    "phase1-plan", "phase2-filter", "phase3-and", "phase4-join",
    "phase4-filtered-join", "phase4-and-join", "direct-intent",
)

CLASSIFIER_PROMPT = """Classify the STRUCTURE of one natural-language SHACL query.
Return JSON only: status (supported or unsupported), operation (one listed
operation or null), reason (nonempty string). Do not invent operations.
Categories:
phase1-plan: retrieval with no conditions and no explicitly shared-owner sibling join.
phase2-filter: one equality filter and no sibling join.
phase3-and: multiple equality filters joined by AND and no sibling join.
phase4-join: explicitly requested sibling result paths sharing an owner, no filters.
phase4-filtered-join: sibling result paths sharing an owner, one equality filter.
phase4-and-join: sibling result paths with multiple AND/OR equality conditions;
also use for OR conditions without sibling paths when the existing operation
supports them. Unsupported properties must still be checked by SHACL grounding.
direct-intent: only when the question explicitly requires direct structured join
intent not represented by the categories above.
If the query requires aggregation, ordering, negation, comparison operators,
unsupported joins, or another unlisted structure, return unsupported and null.
Never classify a query as supported merely because it mentions a known domain.
Do not assess schema feasibility; downstream SHACL validators handle that."""


def _structural_classification(question: str) -> dict | None:
    """Route recognizable supported syntax without relying on model guesses.

    A SHACL traversal (Device -> EndPoint) is NOT a sibling-result join.
    The existing operation-specific validator remains the final authority.
    """
    q = question.strip()
    lower = q.casefold()
    if re.search(r"\\b(how many|count|average|sum|group by|order by|sort|minimum|maximum)\\b", lower):
        return {"status": "unsupported", "operation": None,
                "reason": "Aggregation or ordering is not supported"}
    sibling = bool(re.search(r"\\bplcendpoint\\b", lower) and
                   re.search(r"(?<!plc)\\bendpoint\\b", lower))
    where = re.split(r"\\bwhere\\b", q, maxsplit=1, flags=re.I)
    clause = where[1] if len(where) == 2 else ""
    equality_count = len(re.findall(r"(?<![!<>])=(?!=)", clause))
    # The existing direct-intent operation handles this alternate wording.
    if sibling and not clause and re.search(r"\\bwith\\s+localid\\b", lower):
        operation = "direct-intent"
    elif sibling:
        if equality_count >= 2 or re.search(r"\\b(and|or)\\b", clause, re.I):
            operation = "phase4-and-join"
        elif equality_count == 1:
            operation = "phase4-filtered-join"
        else:
            operation = "phase4-join"
    elif equality_count >= 2 and re.search(r"\\band\\b", clause, re.I):
        operation = "phase3-and"
    elif equality_count == 1 and not re.search(r"\\b(and|or)\\b", clause, re.I):
        operation = "phase2-filter"
    elif not clause or equality_count == 0:
        operation = "phase1-plan"
    else:
        return None
    return {"status": "supported", "operation": operation,
            "reason": "Recognized query structure; SHACL validation is still required"}


def classify_single_domain_query(question: str, *, model="qwen2.5-coder:7b",
                                 endpoint="http://127.0.0.1:11434", transport=None) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty")
    structural = _structural_classification(question)
    if structural is not None:
        return structural
    raw = ollama_select(
        {"question": question, "allowed_operations": list(OPERATIONS)},
        model=model, endpoint=endpoint, transport=transport,
        system_prompt=CLASSIFIER_PROMPT,
    )
    try:
        result = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid query-classification JSON") from exc
    if not isinstance(result, dict) or set(result) != {"status", "operation", "reason"}:
        raise ValueError("Invalid query-classification fields")
    if not isinstance(result["reason"], str) or not result["reason"].strip():
        raise ValueError("Query classification requires a reason")
    if (result["status"] == "supported" and result["operation"] in OPERATIONS
            and isinstance(result["operation"], str)):
        return result
    if result["status"] == "unsupported" and result["operation"] is None:
        return result
    raise ValueError("Invalid query-classification status or operation")
