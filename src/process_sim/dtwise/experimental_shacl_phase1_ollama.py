"""Opt-in Phase 1 Qwen intent/path selector for a single SHACL domain.

No SPARQL compilation or execution. The legacy Qwen selector is unchanged.
"""
from __future__ import annotations

import json

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_query_plan import validate_query_plan
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError

PHASE1_SYSTEM_PROMPT = """You select intent and verified SHACL candidate IDs for ONE domain.
Use only candidate IDs supplied in the user JSON. Never invent paths, properties,
predicates, RDF classes, SPARQL, or cross-domain joins.
Allowed operations: RETRIEVE, COUNT, EXISTS.
RETRIEVE targets a terminal property candidate (P ID, kind=property).
COUNT and EXISTS target a result/shape candidate (R ID, kind=node).
For a selected target set selected_candidate_ids to exactly [target.candidate_id].
Set target.node_index to the final node index of that candidate's path;
the supplied node_count determines this index (node_count - 1).
Do not assume a SHACL NodeShape is an RDF class.
No filters, comparisons, dates, sorting, grouping, aggregation, or other modifiers
are supported. If the question requires any unsupported feature (for example
LocalId = "FI_101"), return unresolved. Do not silently drop constraints.
If several paths are plausible without a uniquely specified owner, return ambiguous.
If no offered candidate answers the question, return unresolved.
For ambiguous/unresolved: selected_candidate_ids=[], operation=null, target=null.
For selected: operation must be one of the three allowed operations, modifiers=[].
Return ONLY JSON with EXACT keys:
status, selected_candidate_ids, operation, target, modifiers, reason.
Target has EXACT keys candidate_id, node_index, kind.
Never generate a predicate IRI or full path in your answer."""


def run_phase1_query_plan(index, prepared: dict, *,
                          model: str = "qwen2.5-coder:7b",
                          endpoint: str = "http://127.0.0.1:11434",
                          transport=None) -> dict:
    """Qualify verified candidates, ask Qwen, validate and resolve selected paths."""
    qualified = qualify_candidates(index, prepared)
    candidates = qualified["prompt"]["candidates"]
    prompt = {
        **qualified["prompt"],
        "allowed_operations": ["RETRIEVE", "COUNT", "EXISTS"],
        "modifiers_allowed": [],
        "candidates": [
            {**c, "node_count": len(qualified["registry"][c["id"]]["node_uris"])}
            for c in candidates
        ],
    }
    if not candidates:
        plan = {
            "status": "unresolved", "selected_candidate_ids": [],
            "operation": None, "target": None, "modifiers": [],
            "reason": "No verified SHACL candidates",
        }
    else:
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                            transport=transport, system_prompt=PHASE1_SYSTEM_PROMPT)
        plan = validate_query_plan(raw, qualified)
        if plan["status"] == "selected":
            cid = plan["target"]["candidate_id"]
            candidate = next(c for c in candidates if c["id"] == cid)
            record = qualified["registry"][cid]
            if record["domain"] != index.domain or candidate["domain"] != index.domain:
                raise SelectionContractError("Selected candidate has wrong domain")
            if (plan["operation"] == "RETRIEVE" and candidate["kind"] != "property"
                    or plan["operation"] in ("COUNT", "EXISTS")
                    and candidate["kind"] != "result"):
                raise SelectionContractError("Operation/qualified candidate kind mismatch")
            if plan["target"]["node_index"] != len(record["node_uris"]) - 1:
                raise SelectionContractError("Target must be terminal node of qualified path")
    selected = [
        {"id": c["id"], "domain": c["domain"], "kind": c["kind"], "path": c["path"]}
        for c in candidates if c["id"] in plan["selected_candidate_ids"]
    ]
    return {"domain": index.domain, "question": qualified["prompt"]["question"],
            "plan": plan, "selected_paths": selected, "qualified": qualified}
