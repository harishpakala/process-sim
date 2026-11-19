"""Opt-in RETRIEVE-only Qwen selection of domain-qualified SHACL property paths.

Qwen selects only verified property candidate IDs; Python owns operation and
path metadata. No filters, joins, SPARQL compilation or execution here.
"""
from __future__ import annotations

import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import validate_selection
from process_sim.dtwise.experimental_shacl_subgraph import _mentioned, _short

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



def _enforce_explicit_shape_owners(index, question: str, selection: dict,
                                   offered: dict) -> dict:
    """Constrain Qwen IDs only when SHACL shape names are explicitly mentioned.

    Prefer the most specific named shapes along a path. Exact identifier
    boundaries prevent EndPoint from matching PLCEndPoint. Unknown synonyms
    are left to semantic retrieval and Qwen, not hard-rejected.
    """
    if selection["status"] != "selected":
        return selection
    explicit = {
        uri for uri, concept in index.shapes.items()
        if any(_mentioned(question, name) for name in [
            *(label for label in concept.get("labels", [])
              if "shacl shape" not in label.casefold()),
            _short(uri),
        ])
    }
    if not explicit:
        return selection
    records = offered["registry"]
    # A named ancestor is context, not a competing property owner.
    # Only suppress a named shape if another named shape occurs after it
    # in at least one verified offered path.
    ancestors = set()
    for record in records.values():
        nodes = record["node_uris"]
        for i, uri in enumerate(nodes):
            if uri in explicit and any(other in explicit for other in nodes[i + 1:]):
                ancestors.add(uri)
    specific = explicit - ancestors
    if not specific:
        return selection
    selected = selection["selected_candidate_ids"]
    retained = [
        cid for cid in selected
        if any(uri in records[cid]["node_uris"] for uri in specific)
    ]
    covered = {
        uri for cid in retained for uri in records[cid]["node_uris"] if uri in specific
    }
    if covered != specific or not retained:
        return {
            "status": "unresolved", "selected_candidate_ids": [],
            "reason": "Qwen did not select verified paths for all explicitly named shapes",
        }
    if retained != selected:
        return {
            **selection, "selected_candidate_ids": retained,
            "reason": selection["reason"] + " (Excluded paths outside explicitly named shapes)",
        }
    return selection


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
        selection = _enforce_explicit_shape_owners(index, question, selection, offered)
    selected = [
        {"id": c["id"], "domain": c["domain"], "kind": c["kind"], "path": c["path"]}
        for c in properties if c["id"] in selection["selected_candidate_ids"]
    ]
    return {
        "domain": index.domain, "question": question,
        "plan": {**selection, "operation": "RETRIEVE" if selection["status"] == "selected" else None},
        "selected_paths": selected, "qualified": qualified,
    }
