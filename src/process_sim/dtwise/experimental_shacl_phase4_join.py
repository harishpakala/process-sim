"""Opt-in Phase 4.1: join two sibling result properties on a verified Device.

Qwen selects property IDs; Python independently grounds the requested ECAD
paths and compiles a single read-only SELECT. No query is executed.
"""
import json
import re

from process_sim.dtwise.experimental_shacl_join_topology import verified_shared_ancestor
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri


PROMPT = """Select exactly TWO verified PROPERTY candidate IDs for a within-domain
join. The user requests EndPoint.Address AND PLCEndPoint.Address belonging
to the SAME Device in ECAD. Select both complete owner paths, not two
independent queries. Do not generate SPARQL or invent graph edges.
Return ONLY JSON with exactly these fields:
status ("selected", "ambiguous", "unresolved"), result_ids (array of two
P IDs for selected; [] otherwise), join_owner ("Device" for selected;
null otherwise), reason (nonempty string).
Abstain on filters, aggregation, unsupported wording, or missing paths."""

FIELDS = {"status", "result_ids", "join_owner", "reason"}
QUESTION = re.compile(
    r"Show\s+(?:the\s+)?EndPoint\s+Address\s+and\s+PLCEndPoint\s+Address"
    r"\s+belonging\s+to\s+the\s+same\s+Device\s+in\s+ECAD\s*[.!]?\s*$",
    re.I,
)


def _expected_paths(qualified):
    paths = {
        c["path"]: c["id"] for c in qualified["prompt"]["candidates"]
        if c["kind"] == "property"
    }
    return (
        paths.get("ECAD → Device → EndPoint → Address"),
        paths.get("ECAD → Device → PLCEndPoint → Address"),
    )


def validate_phase4_join_plan(raw, qualified):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 4.1 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise SelectionContractError("Invalid Phase 4.1 response fields")
    if raw["status"] not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 4.1 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 4.1 reason")
    if raw["status"] != "selected":
        if raw["result_ids"] != [] or raw["join_owner"] is not None:
            raise SelectionContractError("Uncertain join must be empty")
        return raw
    ids = raw["result_ids"]
    if (not isinstance(ids, list) or len(ids) != 2 or
            any(not isinstance(v, str) for v in ids) or len(set(ids)) != 2):
        raise SelectionContractError("Join requires two distinct property IDs")
    expected = _expected_paths(qualified)
    if None in expected or set(ids) != set(expected):
        raise SelectionContractError("Join result semantic grounding mismatch")
    if raw["join_owner"] != "Device":
        raise SelectionContractError("Join owner interpretation mismatch")
    # Preserve Phase 4.1's exact ECAD two-level topology while delegating
    # directed shared-ancestor validation to the schema-derived helper.
    first, second = (qualified["registry"][rid] for rid in expected)
    if (first["domain"] != "ecad" or second["domain"] != "ecad" or
            len(first["node_uris"]) != 3 or len(second["node_uris"]) != 3):
        raise SelectionContractError("No verified shared Device ancestor")
    try:
        topology = verified_shared_ancestor(qualified, list(expected))
    except SelectionContractError as exc:
        raise SelectionContractError("No verified shared Device ancestor") from exc
    if (len(topology["shared_node_uris"]) != 2 or
            topology["ancestor_uri"] != first["node_uris"][1]):
        raise SelectionContractError("No verified shared Device ancestor")
    return raw


def run_phase4_join_plan(index, prepared, *, model="qwen2.5-coder:7b",
                         endpoint="http://127.0.0.1:11434", transport=None):
    qualified = qualify_candidates(index, prepared)
    question = qualified["prompt"]["question"]
    expected = _expected_paths(qualified)
    if index.domain != "ecad" or QUESTION.fullmatch(question.strip()) is None or None in expected:
        plan = {"status": "unresolved", "result_ids": [], "join_owner": None,
                "reason": "Requires two explicit ECAD Address paths joined on the same Device"}
    else:
        prompt = {**qualified["prompt"], "candidates": [
            c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
        ]}
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                           transport=transport, system_prompt=PROMPT)
        plan = validate_phase4_join_plan(raw, qualified)
    return {"domain": index.domain, "question": question,
            "plan": plan, "qualified": qualified}


def compile_phase4_join_sparql(result):
    plan = validate_phase4_join_plan(result["plan"], result["qualified"])
    if plan["status"] != "selected":
        return None
    registry = result["qualified"]["registry"]
    first, second = (registry[rid] for rid in _expected_paths(result["qualified"]))
    shared = first["edges"][0]
    a, b = first["edges"][1], second["edges"][1]
    return ("SELECT DISTINCT ?endpointAddress ?plcAddress WHERE {\n"
            f"  ?ecad {_iri(shared['predicate'])} ?device .\n"
            f"  ?device {_iri(a['predicate'])} ?endpoint .\n"
            f"  ?endpoint {_iri(first['property']['predicate'])} ?endpointAddress .\n"
            f"  ?device {_iri(b['predicate'])} ?plcEndpoint .\n"
            f"  ?plcEndpoint {_iri(second['property']['predicate'])} ?plcAddress .\n"
            "}")
