"""Opt-in RETRIEVE-only Qwen selection of domain-qualified SHACL property paths.

Qwen selects only verified property candidate IDs; Python owns operation and
path metadata. No filters, joins, SPARQL compilation or execution here.
"""
from __future__ import annotations

import re
from time import perf_counter

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import validate_selection
from process_sim.dtwise.experimental_shacl_sparql import compile_selected_paths

PHASE1_SYSTEM_PROMPT = """You select verified SHACL PROPERTY paths in ONE domain.
The only supported task is RETRIEVE (show/find/list property values).
Select ONLY supplied P candidate IDs. Never invent paths, properties, predicates,
RDF classes, SPARQL, or cross-domain joins.
A property name alone does not identify a path: use the complete owner path.
Compare the complete sequence of named shapes and the terminal property.
Treat every shape name as a distinct identifier: EndPoint is NOT PLCEndPoint.
A requested EndPoint path does NOT imply a PLCEndPoint path merely because
one name contains the other. Do not select paths just because they share Address.
Only select a path when its full owner chain satisfies the question.
If the user explicitly asks for multiple paths, select each requested path.
Otherwise do not select sibling branches. For a singular explicit owner, select
only that owner's path. Natural-language synonyms may still identify owners.
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
                          transport=None, timing: dict | None = None) -> dict:
    """Select one or several verified property paths without LLM node indices."""
    t0 = perf_counter()
    qualified = qualify_candidates(index, prepared)
    if timing is not None:
        timing["candidate_qualification_ms"] = (perf_counter() - t0) * 1000
    properties = [c for c in qualified["prompt"]["candidates"]
                  if c["kind"] == "property"]
    question = qualified["prompt"]["question"]
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
        t_llm = perf_counter()
        raw = ollama_select(offered["prompt"], model=model, endpoint=endpoint,
                            transport=transport, system_prompt=PHASE1_SYSTEM_PROMPT)
        if timing is not None:
            timing["qwen_selection_ms"] = (perf_counter() - t_llm) * 1000
        t_validation = perf_counter()
        selection = validate_selection(raw, offered)
        if timing is not None:
            timing["python_validation_ms"] = (perf_counter() - t_validation) * 1000
    if timing is not None:
        timing.setdefault("qwen_selection_ms", 0.0)
        timing.setdefault("python_validation_ms", 0.0)
    # Independently reject the narrow property-only request when the verified
    # schema offers multiple owner paths. Qwen must not resolve this by
    # selecting every matching path (or arbitrarily choosing one).
    bare_request = re.fullmatch(
        r"(?:show|find|list)\\s+(?:the\\s+)?([A-Za-z_][A-Za-z_0-9]*)"
        r"(?:\\s+in\\s+[A-Za-z_][A-Za-z_0-9]*)?\\s*[.!]?\\s*",
        question, flags=re.I,
    )
    if bare_request:
        property_name = bare_request.group(1).casefold()
        matches = [
            candidate for candidate in properties
            if candidate["path"].split(" → ")[-1].casefold() == property_name
        ]
        if len({candidate["path"] for candidate in matches}) > 1:
            selection = {
                "status": "ambiguous", "selected_candidate_ids": [],
                "reason": "Property has multiple verified owner paths; specify the owner",
            }
    selected = [
        {"id": c["id"], "domain": c["domain"], "kind": c["kind"], "path": c["path"]}
        for c in properties if c["id"] in selection["selected_candidate_ids"]
    ]
    return {
        "domain": index.domain, "question": question,
        "plan": {**selection, "operation": "RETRIEVE" if selection["status"] == "selected" else None},
        "selected_paths": selected, "qualified": qualified,
    }


def compile_phase1_sparql(result: dict) -> list[dict]:
    """Compile validated RETRIEVE selections; no model-authored SPARQL."""
    plan = result["plan"]
    if plan["status"] == "selected" and plan["operation"] != "RETRIEVE":
        raise ValueError("Phase 1 supports RETRIEVE only")
    qualified = result["qualified"]
    ids = plan["selected_candidate_ids"]
    property_ids = {c["id"] for c in qualified["prompt"]["candidates"]
                    if c["kind"] == "property"}
    if any(cid not in property_ids for cid in ids):
        raise ValueError("Only verified property candidates can be compiled")
    prepared = {
        "prompt": {**qualified["prompt"], "candidates": [
            c for c in qualified["prompt"]["candidates"] if c["id"] in property_ids
        ]},
        "registry": {cid: {
            "node_uris": record["node_uris"], "edges": record["edges"],
            "property": record["property"],
        } for cid, record in qualified["registry"].items() if cid in property_ids},
    }
    selection = {key: plan[key] for key in
                 ("status", "selected_candidate_ids", "reason")}
    return compile_selected_paths(prepared, selection)
