"""Opt-in Phase 4.3: two AND equality filters on a verified shared Device."""
import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.shacl_planner.operations.phase4_join import (
    _expected_paths, validate_phase4_join_plan, compile_phase4_join_sparql
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri

PROMPT = """Select two ECAD Address result property IDs joined on the SAME Device
and exactly two Device string equality filters joined by AND.
Return ONLY JSON with exactly: status ("selected", "ambiguous", "unresolved"),
result_ids (two P IDs or []), join_owner ("Device" or null),
filters (two objects each with exactly filter_id, owner, property, operator,
value; [] for non-selected), reason (nonempty string).
Filter order MUST match the question: Device.LocalId then Device.DeviceType.
Each owner must be Device, operator must be =, and values must be copied
exactly. Use only offered property IDs. No SPARQL. Abstain if uncertain."""

OR_PROMPT = """Select two ECAD Address result property IDs joined on the SAME Device
and exactly two Device string equality filters joined by OR.
Return ONLY JSON with exactly: status ("selected", "ambiguous", "unresolved"),
result_ids (two P IDs or []), join_owner ("Device" or null),
boolean_operator ("or"), filters (two objects each with exactly filter_id,
owner, property, operator, value; [] for non-selected),
reason (nonempty string).
Filter order MUST match the question: Device.LocalId then Device.DeviceType.
Each owner must be Device, operator must be =, and values must be copied
exactly. Use only offered property IDs. No SPARQL. Abstain if uncertain."""

FIELDS = {"status", "result_ids", "join_owner", "filters", "reason"}
OR_FIELDS = FIELDS | {"boolean_operator"}
FILTER_FIELDS = {"filter_id", "owner", "property", "operator", "value"}
VALUE = r"""(?:"([^"\r\n]*)"|'([^'\r\n]*)'|([A-Za-z_][A-Za-z_0-9.-]*))"""
QUESTION = re.compile(
    r"Show\s+(?:the\s+)?EndPoint\s+Address\s+and\s+PLCEndPoint\s+Address"
    r"\s+belonging\s+to\s+the\s+same\s+Device\s+where\s+"
    r"Device\s+LocalId\s*=\s*" + VALUE +
    r"\s+and\s+Device\s+DeviceType\s*=\s*" + VALUE +
    r"(?:\s+in\s+ECAD)?\s*[.!]?\s*$", re.I,
)

OR_QUESTION = re.compile(QUESTION.pattern.replace(
    r"\s+and\s+Device\s+DeviceType", r"\s+or\s+Device\s+DeviceType"), re.I)

# Phase 5.3: a second, narrowly scoped surface form. Require both
# explicitly named endpoint types, both Device predicates, and AND.
# No general synonym rewriting or guessed graph relationships.
ALTERNATE_QUESTION = re.compile(
    r"Find\s+the\s+addresses\s+of\s+EndPoint\s+and\s+PLCEndPoint"
    r"\s+for\s+devices\s+with\s+LocalId\s+" + VALUE +
    r"\s+and\s+DeviceType\s+" + VALUE +
    r"(?:\s+in\s+ECAD)?\s*[.!]?\s*$", re.I,
)


def _filter_ids(qualified):
    paths = {c["path"]: c["id"] for c in qualified["prompt"]["candidates"]
             if c["kind"] == "property"}
    return (paths.get("ECAD → Device → LocalId"),
            paths.get("ECAD → Device → DeviceType"))


def _literals(question):
    match = (QUESTION.fullmatch(question.strip()) or
             OR_QUESTION.fullmatch(question.strip()) or
             ALTERNATE_QUESTION.fullmatch(question.strip()))
    if match is None:
        return None
    values = match.groups()
    return tuple(next(v for v in values[i:i+3] if v is not None)
                 for i in (0, 3))


def validate_phase4_and_join_plan(raw, qualified):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 4.3 JSON") from exc
    if not isinstance(raw, dict) or set(raw) not in (FIELDS, OR_FIELDS):
        raise SelectionContractError("Invalid Phase 4.3 response fields")
    if set(raw) == OR_FIELDS and raw["boolean_operator"] not in ("and", "or"):
        raise SelectionContractError("Invalid filter boolean operator")
    if raw["status"] not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 4.3 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 4.3 reason")
    if raw["status"] != "selected":
        if raw["result_ids"] != [] or raw["join_owner"] is not None or raw["filters"] != []:
            raise SelectionContractError("Uncertain Phase 4.3 plan must be empty")
        return raw
    question = qualified["prompt"]["question"]
    expected_operator = "or" if OR_QUESTION.fullmatch(question.strip()) else "and"
    if (expected_operator == "or" and set(raw) != OR_FIELDS) or (
            raw.get("boolean_operator", "and") != expected_operator):
        raise SelectionContractError("Filter boolean operator contradicts question")
    validate_phase4_join_plan(
        {k: raw[k] for k in ("status", "result_ids", "join_owner", "reason")},
        qualified)
    ids = _filter_ids(qualified)
    filters = raw["filters"]
    if None in ids or not isinstance(filters, list) or len(filters) != 2:
        raise SelectionContractError("Exactly two verified Device filters required")
    first = qualified["registry"][_expected_paths(qualified)[0]]
    for item, fid, prop in zip(filters, ids, ("LocalId", "DeviceType")):
        if not isinstance(item, dict) or set(item) != FILTER_FIELDS:
            raise SelectionContractError("Invalid Phase 4.3 filter fields")
        if (item["filter_id"] != fid or item["owner"] != "Device" or
                item["property"] != prop or item["operator"] != "=" or
                not isinstance(item["value"], str)):
            raise SelectionContractError("Filter semantic grounding mismatch")
        filtr = qualified["registry"][fid]
        if (filtr["domain"] != "ecad" or len(filtr["node_uris"]) != 2 or
                filtr["node_uris"] != first["node_uris"][:2] or
                filtr["edges"] != first["edges"][:1] or
                filtr["property"]["owner"] != filtr["node_uris"][-1]):
            raise SelectionContractError("Filter must attach to shared Device")
    return raw


def run_phase4_and_join_plan(index, prepared, *, model="qwen2.5-coder:7b",
                             endpoint="http://127.0.0.1:11434", transport=None):
    qualified = qualify_candidates(index, prepared)
    question = qualified["prompt"]["question"]
    literals = _literals(question)
    is_or = OR_QUESTION.fullmatch(question.strip()) is not None
    if (index.domain != "ecad" or literals is None or
            None in _expected_paths(qualified) or None in _filter_ids(qualified)):
        plan = {"status": "unresolved", "result_ids": [], "join_owner": None,
                "filters": [], "reason": "Requires verified ECAD shared-Device join with LocalId AND DeviceType equality"}
    else:
        prompt = {**qualified["prompt"], "candidates": [
            c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
        ]}
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                           transport=transport,
                           system_prompt=OR_PROMPT if is_or else PROMPT)
        plan = validate_phase4_and_join_plan(raw, qualified)
        if plan["status"] == "selected" and tuple(f["value"] for f in plan["filters"]) != literals:
            raise SelectionContractError("Filter literals do not match question")
    # Additive Phase 5.4 artifact: constructed only after independent validation.
    # Lazy import avoids a module-level cycle with the intent adapter.
    intent = None
    if plan["status"] == "selected" and not is_or:
        from process_sim.dtwise.shacl_planner.planning.query_intent import validated_join_intent
        intent = validated_join_intent(plan, qualified)
    return {"domain": index.domain, "question": question, "plan": plan,
            "qualified": qualified, "intent": intent}


def compile_phase4_and_join_sparql(result):
    plan = validate_phase4_and_join_plan(result["plan"], result["qualified"])
    if plan["status"] != "selected":
        return None
    literals = _literals(result["question"])
    if literals is None or tuple(f["value"] for f in plan["filters"]) != literals:
        raise SelectionContractError("Filter literals do not match question")
    base = compile_phase4_join_sparql({
        "plan": {k: plan[k] for k in ("status", "result_ids", "join_owner", "reason")},
        "qualified": result["qualified"],
    })
    lines = []
    is_or = plan.get("boolean_operator") == "or"
    for i, item in enumerate(plan["filters"], 1):
        filtr = result["qualified"]["registry"][item["filter_id"]]
        triple = f"?device {_iri(filtr['property']['predicate'])} ?filterValue{i} ."
        if is_or:
            lines.append(f"  OPTIONAL {{ {triple} }}")
        else:
            lines.append(f"  {triple}")
            lines.append(f"  FILTER(?filterValue{i} = {json.dumps(literals[i-1], ensure_ascii=False)})")
    if is_or:
        expressions = [
            f'(?filterValue{i} = {json.dumps(value, ensure_ascii=False)})'
            for i, value in enumerate(literals, 1)
        ]
        lines.append("  FILTER(" + " || ".join(expressions) + ")")
    return base[:-1] + "\n".join(lines) + "\n}"
