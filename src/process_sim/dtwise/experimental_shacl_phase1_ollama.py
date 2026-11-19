"""Opt-in RETRIEVE-only Qwen selection of domain-qualified SHACL property paths.

Qwen selects only verified property candidate IDs; Python owns operation and
path metadata. No filters, joins, SPARQL compilation or execution here.
"""
from __future__ import annotations

import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import validate_selection

PHASE1_SYSTEM_PROMPT = """You select verified SHACL PROPERTY paths in ONE domain.
The only supported task is RETRIEVE (show/find/list property values).
Select ONLY supplied P candidate IDs. Never invent paths, properties, predicates,
RDF classes, SPARQL, or cross-domain joins.
A property name alone does not identify a path: use the complete owner path.
If the user explicitly asks for multiple paths (both EndPoint and PLCEndPoint),
select each requested property path. Otherwise do not select sibling branches.
If multiple paths remain plausible without a specified owner, return ambiguous.
If no offered path answers the question, return unresolved.
COUNT, EXISTS, filters (e.g. LocalId = "FI_101"), sorting, grouping, date
constraints and aggregation are NOT supported: return unresolved rather than
dropping any part of the question.
Return ONLY JSON with EXACT keys:
status ("selected", "ambiguous", or "unresolved"),
selected_candidate_ids (array of offered P IDs), reason (nonempty string).
For ambiguous/unresolved selected_candidate_ids must be [].
Do NOT output node_index, target, operation, modifiers or path strings."""


def run_phase1_query_plan(index, prepared: dict, *,
                          model: str = "qwen2.5-coder:7b",
                          endpoint: str = "http://127.0.0.1:11434",
                          transport=None) -> dict:
    """Select one or several verified property paths without LLM node indices."""
    qualified = qualify_candidates(index, prepared)
    properties = [c for c in qualified["prompt"]["candidates"]
                  if c["kind"] == "property"]
    offered = {
        "prompt": {**qualified["prompt"], "candidates": properties},
        "registry": {c["id"]: qualified["registry"][c["id"]] for c in properties},
    }
    question = offered["prompt"]["question"]
    # Conservative fail-closed guard for explicit unsupported operations.
    # This is not a full natural-language intent detector.
    unsupported = bool(re.search(
        r"\b(how many|count|does (?:any|a|an)|is there|are there|"
        r"average|sum|minimum|maximum|sort|order by|group by)\b",
        question, re.I,
    )) or bool(re.search(r"\b[A-Za-z_][A-Za-z_0-9]*\s*(?:=|!=|<=|>=|<|>)\s*[\"'0-9]", question))
    if unsupported or not properties:
        selection = {
            "status": "unresolved", "selected_candidate_ids": [],
            "reason": ("Unsupported operation or filter in RETRIEVE-only Phase 1"
                       if unsupported else "No verified SHACL property candidates"),
        }
    else:
        raw = ollama_select(offered["prompt"], model=model, endpoint=endpoint,
                            transport=transport, system_prompt=PHASE1_SYSTEM_PROMPT)
        selection = validate_selection(raw, offered)
    selected = [
        {"id": c["id"], "domain": c["domain"], "kind": c["kind"], "path": c["path"]}
        for c in properties if c["id"] in selection["selected_candidate_ids"]
    ]
    return {
        "domain": index.domain, "question": question,
        "plan": {**selection, "operation": "RETRIEVE" if selection["status"] == "selected" else None},
        "selected_paths": selected, "qualified": qualified,
    }
