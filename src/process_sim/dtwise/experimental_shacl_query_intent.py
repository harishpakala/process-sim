"""Phase 5.4: schema-verified structured intent for the ECAD two-filter join.

An additive representation of a validated planner selection, not a new
source of truth. Never compile a model-supplied intent without validation.
"""
from process_sim.dtwise.experimental_shacl_phase4_join import _expected_paths
from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    _filter_ids, _literals, validate_phase4_and_join_plan,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def validated_join_intent(plan, qualified):
    """Build a structured intent only from independently verified selections."""
    verified = validate_phase4_and_join_plan(plan, qualified)
    if verified["status"] != "selected":
        raise SelectionContractError("Cannot build intent from unresolved selection")
    domain = qualified["prompt"]["domain"]
    if domain != "ecad":
        raise SelectionContractError("Unsupported structured join domain")
    values = _literals(qualified["prompt"]["question"])
    if values is None or tuple(f["value"] for f in verified["filters"]) != values:
        raise SelectionContractError("Intent filter literals contradict question")
    expected = _expected_paths(qualified)
    filters = _filter_ids(qualified)
    return {
        "domain": domain,
        "operation": "select",
        "result_property_ids": list(expected),
        "join": {"kind": "shared_ancestor", "owner": "Device"},
        "boolean_operator": "and",
        "filters": [
            {"property_id": fid, "owner": "Device", "property": name,
             "operator": "=", "value": value}
            for fid, name, value in zip(filters, ("LocalId", "DeviceType"), values)
        ],
    }


# Phase 5.4 increment 2: direct model-proposed intent, fail-closed.
# Keep this separate from the existing Phase 4.3 selection pipeline.
import json

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_graph_evidence import graph_evidence
from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    compile_phase4_and_join_sparql,
)

DIRECT_INTENT_PROMPT = """Propose a structured ECAD read-only SELECT intent.
Use ONLY supplied SHACL-qualified property candidate IDs.
Use the supplied directed SHACL subgraph nodes, edges, and property predicates
to reason about common ancestors and filter ownership. Do not invent edges.
For the two requested Address results joined on the SAME Device and
Device LocalId AND DeviceType equality filters, return ONLY JSON:
domain: "ecad", operation: "select",
result_property_ids: array of exactly two supplied P IDs,
join: {"kind":"shared_ancestor","owner":"Device"},
boolean_operator: "and",
filters: array of exactly two objects with property_id, owner,
property, operator, value. Use Device LocalId then DeviceType;
operator must be "="; copy question values exactly.
If uncertain, do not fabricate: return JSON null.
No SPARQL, no invented predicates, no extra keys."""

INTENT_FIELDS = {
    "domain", "operation", "result_property_ids", "join",
    "boolean_operator", "filters",
}
INTENT_FILTER_FIELDS = {"property_id", "owner", "property", "operator", "value"}


def validate_proposed_join_intent(raw, qualified):
    """Reject model fabrications; reuse the existing topology/semantic validator."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise SelectionContractError("Invalid structured intent JSON") from exc
    if not isinstance(raw, dict) or set(raw) != INTENT_FIELDS:
        raise SelectionContractError("Invalid structured intent fields")
    if (raw["domain"] != "ecad" or
            raw["domain"] != qualified["prompt"]["domain"] or
            raw["operation"] != "select" or
            raw["boolean_operator"] != "and" or
            raw["join"] != {"kind": "shared_ancestor", "owner": "Device"}):
        raise SelectionContractError("Unsupported structured intent semantics")
    results = raw["result_property_ids"]
    filters = raw["filters"]
    if (not isinstance(results, list) or len(results) != 2 or
            not isinstance(filters, list) or len(filters) != 2):
        raise SelectionContractError("Incorrect structured intent arity")
    if any(not isinstance(f, dict) or set(f) != INTENT_FILTER_FIELDS
           for f in filters):
        raise SelectionContractError("Invalid structured intent filter fields")
    legacy = {
        "status": "selected",
        "result_ids": results,
        "join_owner": "Device",
        "filters": [
            {"filter_id": f["property_id"], "owner": f["owner"],
             "property": f["property"], "operator": f["operator"],
             "value": f["value"]}
            for f in filters
        ],
        "reason": "Direct structured intent, independently verified",
    }
    validated_join_intent(legacy, qualified)
    return raw


def run_direct_join_intent(index, prepared, *, model="qwen2.5-coder:7b",
                           endpoint="http://127.0.0.1:11434", transport=None):
    """Opt-in direct Ollama intent; return no query for unsupported questions."""
    from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
    qualified = qualify_candidates(index, prepared)
    question = qualified["prompt"]["question"]
    if (index.domain != "ecad" or _literals(question) is None or
            None in _expected_paths(qualified) or None in _filter_ids(qualified)):
        return {"domain": index.domain, "question": question, "intent": None,
                "qualified": qualified, "sparql": None,
                "reason": "Unsupported or ungrounded direct join intent"}
    prompt = {**qualified["prompt"], "candidates": [
        c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
    ]}
    prompt["shacl_subgraph"] = graph_evidence(qualified)
    raw = ollama_select(prompt, model=model, endpoint=endpoint,
                        transport=transport, system_prompt=DIRECT_INTENT_PROMPT)
    if raw.strip() == "null":
        return {"domain": index.domain, "question": question, "intent": None,
                "qualified": qualified, "sparql": None,
                "reason": "Model abstained"}
    intent = validate_proposed_join_intent(raw, qualified)
    plan = {
        "status": "selected", "result_ids": intent["result_property_ids"],
        "join_owner": "Device",
        "filters": [
            {"filter_id": f["property_id"], "owner": f["owner"],
             "property": f["property"], "operator": f["operator"],
             "value": f["value"]}
            for f in intent["filters"]
        ],
        "reason": "Direct structured intent, independently verified",
    }
    sparql = compile_phase4_and_join_sparql({
        "plan": plan, "qualified": qualified, "question": question,
    })
    return {"domain": index.domain, "question": question, "intent": intent,
            "qualified": qualified, "sparql": sparql}
