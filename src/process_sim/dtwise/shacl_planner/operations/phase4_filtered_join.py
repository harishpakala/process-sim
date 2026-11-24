"""Opt-in Phase 4.2: verified sibling join with one Device.LocalId equality filter."""
import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.shacl_planner.operations.phase4_join import  (
    _expected_paths, validate_phase4_join_plan, compile_phase4_join_sparql,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri


PROMPT = """Plan exactly two ECAD Address results joined on the SAME Device, with
one Device.LocalId string equality filter. Select verified PROPERTY IDs only.
Return ONLY JSON with exactly: status ("selected", "ambiguous", "unresolved"),
result_ids (two P IDs, or []), join_owner ("Device" or null),
filter_id (P ID or null), filter_owner ("Device" or null),
filter_property ("LocalId" or null), operator ("=" or null),
value (literal string or null), reason (nonempty string).
Do not write SPARQL. Do not invent IDs, properties, or values.
Abstain on other filters, domains, joins, aggregation or ambiguous requests."""

FIELDS = {"status", "result_ids", "join_owner", "filter_id", "filter_owner",
          "filter_property", "operator", "value", "reason"}
QUESTION = re.compile(
    r"Show\s+(?:the\s+)?EndPoint\s+Address\s+and\s+PLCEndPoint\s+Address"
    r"\s+belonging\s+to\s+the\s+same\s+Device\s+where\s+Device\s+LocalId"
    r"\s*=\s*(?:\"(?P<double>[^\"\r\n]*)\"|'(?P<single>[^'\r\n]*)'|"
    r"(?P<bare>[A-Za-z_][A-Za-z_0-9.-]*))\s+in\s+ECAD\s*[.!]?\s*$",
    re.I,
)


def _filter_id(qualified):
    ids = [c["id"] for c in qualified["prompt"]["candidates"]
           if c["kind"] == "property" and c["path"] == "ECAD → Device → LocalId"]
    return ids[0] if len(ids) == 1 else None


def validate_phase4_filtered_join_plan(raw, qualified):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 4.2 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise SelectionContractError("Invalid Phase 4.2 response fields")
    if raw["status"] not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 4.2 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 4.2 reason")
    if raw["status"] != "selected":
        if raw["result_ids"] != [] or any(raw[k] is not None for k in
                ("join_owner", "filter_id", "filter_owner", "filter_property", "operator", "value")):
            raise SelectionContractError("Uncertain Phase 4.2 plan must be empty")
        return raw
    validate_phase4_join_plan(
        {k: raw[k] for k in ("status", "result_ids", "join_owner", "reason")}, qualified)
    fid = _filter_id(qualified)
    if fid is None or raw["filter_id"] != fid:
        raise SelectionContractError("Filter property semantic grounding mismatch")
    if (raw["filter_owner"] != "Device" or raw["filter_property"] != "LocalId"
            or raw["operator"] != "=" or not isinstance(raw["value"], str)):
        raise SelectionContractError("Invalid Device.LocalId equality interpretation")
    filtr = qualified["registry"][fid]
    first = qualified["registry"][_expected_paths(qualified)[0]]
    if (filtr["domain"] != "ecad" or len(filtr["node_uris"]) != 2 or
            filtr["node_uris"] != first["node_uris"][:2] or
            filtr["edges"] != first["edges"][:1] or
            filtr["property"]["owner"] != filtr["node_uris"][-1]):
        raise SelectionContractError("Filter must attach to shared Device")
    return raw


def run_phase4_filtered_join_plan(index, prepared, *, model="qwen2.5-coder:7b",
                                  endpoint="http://127.0.0.1:11434", transport=None):
    qualified = qualify_candidates(index, prepared)
    question = qualified["prompt"]["question"]
    match = QUESTION.fullmatch(question.strip())
    if (index.domain != "ecad" or match is None or
            None in _expected_paths(qualified) or _filter_id(qualified) is None):
        plan = {"status": "unresolved", "result_ids": [], "join_owner": None,
                "filter_id": None, "filter_owner": None, "filter_property": None,
                "operator": None, "value": None,
                "reason": "Requires explicit same-Device ECAD Address join with one Device.LocalId equality"}
    else:
        prompt = {**qualified["prompt"], "candidates": [
            c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
        ]}
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                           transport=transport, system_prompt=PROMPT)
        plan = validate_phase4_filtered_join_plan(raw, qualified)
        literal = next(v for v in match.group("double", "single", "bare") if v is not None)
        if plan["status"] == "selected" and plan["value"] != literal:
            raise SelectionContractError("Filter value does not match question literal")
    return {"domain": index.domain, "question": question, "plan": plan,
            "qualified": qualified}


def compile_phase4_filtered_join_sparql(result):
    plan = validate_phase4_filtered_join_plan(result["plan"], result["qualified"])
    if plan["status"] != "selected":
        return None
    match = QUESTION.fullmatch(result["question"].strip())
    if match is None:
        raise SelectionContractError("Question does not ground Phase 4.2 filter")
    literal = next(v for v in match.group("double", "single", "bare") if v is not None)
    if plan["value"] != literal:
        raise SelectionContractError("Filter value does not match question literal")
    base = compile_phase4_join_sparql({
        "plan": {k: plan[k] for k in ("status", "result_ids", "join_owner", "reason")},
        "qualified": result["qualified"],
    })
    filtr = result["qualified"]["registry"][plan["filter_id"]]
    return (base[:-1] +
            f"  ?device {_iri(filtr['property']['predicate'])} ?filterValue .\n"
            f"  FILTER(?filterValue = {json.dumps(literal, ensure_ascii=False)})\n"
            "}")
