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
result_ids lists ALL requested output properties (one or more). filter_id identifies the
property compared to the string literal. Match complete owner chains:
EndPoint and PLCEndPoint are distinct. The filter property owner must be on
the result path (an ancestor or the result owner), not a sibling branch.
Copy the string value from the user's question exactly; do not invent values.
Values may be quoted strings or unquoted identifier tokens such as FI_101.
If unsupported, ambiguous, or missing a matching candidate, abstain.
Return ONLY JSON with exactly these keys:
status ("selected", "ambiguous", "unresolved"), result_ids (array of P IDs),
filter_id (P ID or null), operator ("=" or null), value (string or null),
reason (nonempty string). For non-selected statuses result_ids must be []
and filter_id, operator, value must be null.
If the question explicitly asks for both EndPoint and PLCEndPoint, include BOTH
Address paths. Never add sibling paths unless requested. A shared Device filter
may apply to both results; do not combine branches into a single query.
No COUNT, EXISTS, AND, OR, comparisons, numeric values, or cross-domain joins."""

FIELDS = {"status", "result_ids", "filter_id", "operator", "value", "reason"}
LEGACY_FIELDS = {"status", "result_id", "filter_id", "operator", "value", "reason"}
_LITERAL = re.compile(r"""(?<!\w)(?:=|equals?)\s*(?:["']([^"'\r\n]*)["']|([A-Za-z_][A-Za-z_0-9.-]*))""", re.I)


def validate_filter_plan(raw, qualified: dict) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 2 JSON") from exc
    if isinstance(raw, dict) and set(raw) == LEGACY_FIELDS:
        raw = {**raw, "result_ids": ([raw["result_id"]] if raw["result_id"] is not None else [])}
        del raw["result_id"]
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise SelectionContractError("Invalid Phase 2 response fields")
    status = raw["status"]
    if status not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 2 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 2 reason")
    fields = ("filter_id", "operator", "value")
    if status != "selected":
        if raw["result_ids"] != [] or any(raw[key] is not None for key in fields):
            raise SelectionContractError("Uncertain Phase 2 plan must have null fields")
        return raw
    offered = {c["id"] for c in qualified["prompt"]["candidates"] if c["kind"] == "property"}
    ids = raw["result_ids"]
    if (not isinstance(ids, list) or not ids or
            any(not isinstance(item, str) for item in ids) or
            len(ids) != len(set(ids)) or
            any(item not in offered for item in ids) or raw["filter_id"] not in offered):
        raise SelectionContractError("Unknown or non-property Phase 2 candidate ID")
    if raw["operator"] != "=" or not isinstance(raw["value"], str):
        raise SelectionContractError("Only string equality is supported")
    filtr = qualified["registry"][raw["filter_id"]]
    # Validate the shared ancestor path independently for every result.
    for result_id in ids:
        result = qualified["registry"][result_id]
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
    literals = [quoted if quoted != "" else unquoted
                for quoted, unquoted in _LITERAL.findall(question)]
    filter_clause = re.split(r"\bwhere\b", question, maxsplit=1, flags=re.I)[-1]
    unsupported = bool(re.search(
        r"\b(how many|count|exists|does any|is there|are there|average|sum|"
        r"group by|order by|greater than|less than)\b|(?:!=|<=|>=|<|>)", question, re.I
    )) or len(literals) != 1 or bool(re.search(r"\b(and|or)\b", filter_clause, re.I))
    if unsupported or not offered["prompt"]["candidates"]:
        plan = {"status": "unresolved", "result_ids": [], "filter_id": None,
                "operator": None, "value": None,
                "reason": "Unsupported or missing single string equality filter/candidates"}
    else:
        raw = ollama_select(offered["prompt"], model=model, endpoint=endpoint,
                            transport=transport, system_prompt=PROMPT)
        plan = validate_filter_plan(raw, qualified)
        # An explicit result owner constrains the LLM's selected result paths.
        # Match complete shape tokens: EndPoint must not match PLCEndPoint.
        if plan["status"] == "selected":
            result_candidates = {
                c["id"]: c for c in offered["prompt"]["candidates"]
                if c["id"] != plan["filter_id"]
            }
            owners = {
                cid: candidate["path"].split(" → ")[-2]
                for cid, candidate in result_candidates.items()
                if len(candidate["path"].split(" → ")) >= 2
            }
            mentioned = {
                owner for owner in set(owners.values())
                if re.search(r"(?<![A-Za-z_0-9])" + re.escape(owner)
                             + r"(?![A-Za-z_0-9])", question, re.I)
            }
            if len(mentioned) == 1:
                explicit_owner = next(iter(mentioned))
                kept = [cid for cid in plan["result_ids"]
                        if owners.get(cid, "").casefold() == explicit_owner.casefold()]
                if kept and len(kept) != len(plan["result_ids"]):
                    plan = {**plan, "result_ids": kept,
                            "reason": "Explicit result owner excludes unrequested sibling paths"}
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
    filtr = registry[plan["filter_id"]]
    queries = []
    for result_id in plan["result_ids"]:
        selected = registry[result_id]
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
        queries.append({"result_id": result_id, "filter_id": plan["filter_id"],
                        "sparql": "SELECT DISTINCT ?value WHERE {\n" + "\n".join(triples) + "\n}"})
    return queries
