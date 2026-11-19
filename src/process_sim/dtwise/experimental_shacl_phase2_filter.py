"""Opt-in Phase 2: one equality filter on a verified ancestor property path.

Qwen chooses IDs and a literal; Python validates structure and writes SPARQL.
No execution, cross-branch joins, or changes to RETRIEVE-only Phase 1.
"""
from __future__ import annotations

import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri

PROMPT = """Plan a single-domain RETRIEVE query with exactly ONE equality filter.
Choose supplied verified PROPERTY candidate IDs only. Do not write SPARQL.
result_id identifies the requested output property. filter_id identifies the
property compared to the string literal. Match complete owner chains:
EndPoint and PLCEndPoint are distinct. The filter property owner must be on
the result path (an ancestor or the result owner), not a sibling branch.
Copy the string value from the user's question exactly; do not invent values.
If unsupported, ambiguous, or missing a matching candidate, abstain.
Return ONLY JSON with exactly these keys:
status ("selected", "ambiguous", "unresolved"), result_id (P ID or null),
filter_id (P ID or null), operator ("=" or null), value (string or null),
reason (nonempty string). For non-selected statuses all four plan fields null.
No COUNT, EXISTS, AND, OR, comparisons, numeric values, or cross-domain joins."""

FIELDS = {"status", "result_id", "filter_id", "operator", "value", "reason"}
_LITERAL = re.compile(r"""(?<!\w)(?:=|equals?)(?:\s*)["']([^"'\r\n]*)["']""", re.I)


def validate_filter_plan(raw, qualified: dict) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 2 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise SelectionContractError("Invalid Phase 2 response fields")
    status = raw["status"]
    if status not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 2 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 2 reason")
    fields = ("result_id", "filter_id", "operator", "value")
    if status != "selected":
        if any(raw[key] is not None for key in fields):
            raise SelectionContractError("Uncertain Phase 2 plan must have null fields")
        return raw
    offered = {c["id"] for c in qualified["prompt"]["candidates"] if c["kind"] == "property"}
    if raw["result_id"] not in offered or raw["filter_id"] not in offered:
        raise SelectionContractError("Unknown or non-property Phase 2 candidate ID")
    if raw["operator"] != "=" or not isinstance(raw["value"], str):
        raise SelectionContractError("Only string equality is supported")
    result = qualified["registry"][raw["result_id"]]
    filtr = qualified["registry"][raw["filter_id"]]
    # An ancestor property can attach to an existing result-chain variable.
    prefix = filtr["node_uris"]
    if result["node_uris"][:len(prefix)] != prefix:
        raise SelectionContractError("Filter owner must be on the result path")
    if filtr["edges"] != result["edges"][:len(filtr["edges"])]:
        raise SelectionContractError("Filter edges do not share the result path")
    return raw


def run_phase2_filter_plan(index, prepared: dict, *, model="qwen2.5-coder:7b",
                           endpoint="http://127.0.0.1:11434", transport=None) -> dict:
    qualified = qualify_candidates(index, prepared)
    offered = {"prompt": {**qualified["prompt"], "candidates": [
        c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
    ]}, "registry": qualified["registry"]}
    question = offered["prompt"]["question"]
    # Fail closed for requests outside the one-string-equality scope.
    literals = _LITERAL.findall(question)
    unsupported = bool(re.search(
        r"\b(how many|count|exists|does any|is there|are there|average|sum|"
        r"group by|order by|greater than|less than)\b|(?:!=|<=|>=|<|>)", question, re.I
    )) or len(literals) != 1 or bool(re.search(r"\b(and|or)\b", question, re.I))
    if unsupported or not offered["prompt"]["candidates"]:
        plan = {"status": "unresolved", "result_id": None, "filter_id": None,
                "operator": None, "value": None,
                "reason": "Unsupported or missing single string equality filter/candidates"}
    else:
        raw = ollama_select(offered["prompt"], model=model, endpoint=endpoint,
                            transport=transport, system_prompt=PROMPT)
        plan = validate_filter_plan(raw, qualified)
        # Ground literal in the user's question; never accept a fabricated value.
        if plan["status"] == "selected" and plan["value"] != literals[0]:
            raise SelectionContractError("Filter value does not match question literal")
    return {"domain": index.domain, "question": question, "plan": plan,
            "qualified": qualified}


def compile_phase2_filter_sparql(result: dict) -> list[dict]:
    plan = validate_filter_plan(result["plan"], result["qualified"])
    if plan["status"] != "selected":
        return []
    registry = result["qualified"]["registry"]
    selected = registry[plan["result_id"]]
    filtr = registry[plan["filter_id"]]
    nodes = selected["node_uris"]
    triples = []
    for i, edge in enumerate(selected["edges"]):
        if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
            raise ValueError("Disconnected result path")
        triples.append(f"  ?n{i} {_iri(edge['predicate'])} ?n{i + 1} .")
    if selected["property"]["owner"] != nodes[-1]:
        raise ValueError("Invalid result property owner")
    if filtr["property"]["owner"] != filtr["node_uris"][-1]:
        raise ValueError("Invalid filter property owner")
    triples.append(f"  ?n{len(nodes)-1} {_iri(selected['property']['predicate'])} ?value .")
    triples.append(f"  ?n{len(filtr['node_uris'])-1} {_iri(filtr['property']['predicate'])} ?filterValue .")
    triples.append(f"  FILTER(?filterValue = {json.dumps(plan['value'], ensure_ascii=False)})")
    return [{"result_id": plan["result_id"], "filter_id": plan["filter_id"],
             "sparql": "SELECT DISTINCT ?value WHERE {\n" + "\n".join(triples) + "\n}"}]
