"""Opt-in Phase 3: one result property and exactly two AND equality filters.

Qwen selects verified property IDs; Python checks path ownership and literal
grounding and compiles read-only SPARQL without executing it.
"""
import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_phase2_filter import _LITERAL
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri

PROMPT = """Plan one RETRIEVE result with exactly TWO string equality filters joined by AND.
Use only verified PROPERTY candidate IDs. Do not write SPARQL.
Return ONLY JSON with exactly: status ("selected", "ambiguous", "unresolved"),
result_id (P ID or null), filters (array of two objects each with exactly
filter_id (P ID), owner (string), property (string), operator ("="), 
value (string)), result_meaning (string or null), reason (nonempty string).
For selected status, result_meaning must be the complete owner.property
(e.g. EndPoint.Address), and each filter owner/property must describe
the selected candidate exactly.
For non-selected status use result_id null, result_meaning null and filters [].
Both filter owners must be on the result path, either ancestor or result owner.
Copy literal values exactly from the question and keep their condition order.
No OR, COUNT, EXISTS, numeric comparison, aggregation, cross-branch joins or
multiple result properties. Abstain if unsupported or ambiguous."""

FIELDS = {"status", "result_id", "result_meaning", "filters", "reason"}
FILTER_FIELDS = {"filter_id", "owner", "property", "operator", "value"}
UNSUPPORTED = re.compile(
    r"\b(how many|count|exists|does any|is there|are there|average|sum|"
    r"group by|order by|greater than|less than)\b|(?:!=|<=|>=|<|>)", re.I
)


def validate_phase3_plan(raw, qualified):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid Phase 3 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise SelectionContractError("Invalid Phase 3 response fields")
    if raw["status"] not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 3 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 3 reason")
    if raw["status"] != "selected":
        if raw["result_id"] is not None or raw["result_meaning"] is not None or raw["filters"] != []:
            raise SelectionContractError("Uncertain Phase 3 plan must be empty")
        return raw
    offered = {c["id"] for c in qualified["prompt"]["candidates"]
               if c["kind"] == "property"}
    if raw["result_id"] not in offered:
        raise SelectionContractError("Unknown result property ID")
    filters = raw["filters"]
    if not isinstance(filters, list) or len(filters) != 2:
        raise SelectionContractError("Exactly two filters required")
    result = qualified["registry"][raw["result_id"]]
    result_candidate = next(c for c in qualified["prompt"]["candidates"]
                            if c["id"] == raw["result_id"])
    result_path = result_candidate["path"]
    expected_meaning = ".".join(result_path.split(" → ")[-2:])
    if raw["result_meaning"] != expected_meaning:
        raise SelectionContractError("Result interpretation does not match candidate")
    for item in filters:
        if not isinstance(item, dict) or set(item) != FILTER_FIELDS:
            raise SelectionContractError("Invalid Phase 3 filter fields")
        if item["filter_id"] not in offered:
            raise SelectionContractError("Unknown filter property ID")
        if item["operator"] != "=" or not isinstance(item["value"], str):
            raise SelectionContractError("Only string equality supported")
        filtr = qualified["registry"][item["filter_id"]]
        candidate = next(c for c in qualified["prompt"]["candidates"]
                         if c["id"] == item["filter_id"])
        parts = candidate["path"].split(" → ")
        if item["owner"] != parts[-2] or item["property"] != parts[-1]:
            raise SelectionContractError("Filter interpretation does not match candidate")
        prefix = filtr["node_uris"]
        if result["node_uris"][:len(prefix)] != prefix:
            raise SelectionContractError("Filter owner must be on result path")
        if filtr["edges"] != result["edges"][:len(filtr["edges"])]:
            raise SelectionContractError("Filter edges must share result path")
    if len({(f["filter_id"], f["value"]) for f in filters}) != 2:
        raise SelectionContractError("Duplicate filter condition")
    return raw



def _explicit_filter_constraints(clause, qualified):
    """Recognize only exact schema owner/property labels in two AND clauses."""
    labels = {(parts[-2], parts[-1])
              for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
              for parts in [c["path"].split(" → ")] if len(parts) >= 2}
    pieces = re.split(r"\band\b", clause, flags=re.I)
    if len(pieces) != 2:
        return None
    constraints = []
    for piece in pieces:
        matches = []
        for owner, prop in labels:
            pattern = (r"^\s*" + re.escape(owner) + r"\s+" +
                       re.escape(prop) +
                       r"""\s*=\s*(?:"([^"\r\n]*)"|'([^'\r\n]*)'|([A-Za-z_][A-Za-z_0-9.-]*))(?:\s+in\s+\w+)?\s*$""")
            found = re.fullmatch(pattern, piece, flags=re.I)
            if found:
                matches.append((owner, prop, next(v for v in found.groups() if v is not None)))
        if len(matches) != 1:
            return None
        constraints.append(matches[0])
    return constraints

def run_phase3_and_plan(index, prepared, *, model="qwen2.5-coder:7b",
                        endpoint="http://127.0.0.1:11434", transport=None):
    qualified = qualify_candidates(index, prepared)
    prompt = {**qualified["prompt"], "candidates": [
        c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
    ]}
    question = prompt["question"]
    clause_parts = re.split(r"\bwhere\b", question, maxsplit=1, flags=re.I)
    clause = clause_parts[1] if len(clause_parts) == 2 else ""
    literals = [quoted if quoted != "" else unquoted
                for quoted, unquoted in _LITERAL.findall(clause)]
    supported = (len(literals) == 2 and
                 len(re.findall(r"\band\b", clause, re.I)) == 1 and
                 not re.search(r"\bor\b", clause, re.I) and
                 not UNSUPPORTED.search(question) and bool(prompt["candidates"]))
    grounding = _explicit_filter_constraints(clause, qualified) if supported else None
    if grounding is None:
        supported = False
    if not supported:
        plan = {"status": "unresolved", "result_id": None, "result_meaning": None, "filters": [],
                "reason": "Requires exactly two AND string equality conditions"}
    else:
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                           transport=transport, system_prompt=PROMPT)
        plan = validate_phase3_plan(raw, qualified)
        if plan["status"] == "selected":
            if [f["value"] for f in plan["filters"]] != literals:
                raise SelectionContractError("Filter values do not match question literals")
            for item, (owner, prop, value) in zip(plan["filters"], grounding):
                if (item["owner"].casefold(), item["property"].casefold(), item["value"]) != (
                        owner.casefold(), prop.casefold(), value):
                    raise SelectionContractError("Filter semantic grounding mismatch")
    return {"domain": index.domain, "question": question,
            "plan": plan, "qualified": qualified}


def compile_phase3_and_sparql(result):
    plan = validate_phase3_plan(result["plan"], result["qualified"])
    if plan["status"] != "selected":
        return None
    registry = result["qualified"]["registry"]
    selected = registry[plan["result_id"]]
    nodes = selected["node_uris"]
    triples = []
    for i, edge in enumerate(selected["edges"]):
        if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
            raise ValueError("Disconnected result path")
        triples.append(f"  ?n{i} {_iri(edge['predicate'])} ?n{i + 1} .")
    if selected["property"]["owner"] != nodes[-1]:
        raise ValueError("Invalid result property owner")
    triples.append(f"  ?n{len(nodes)-1} {_iri(selected['property']['predicate'])} ?value .")
    for i, item in enumerate(plan["filters"], 1):
        filtr = registry[item["filter_id"]]
        if filtr["property"]["owner"] != filtr["node_uris"][-1]:
            raise ValueError("Invalid filter property owner")
        var = f"?filterValue{i}"
        triples.append(f"  ?n{len(filtr['node_uris'])-1} {_iri(filtr['property']['predicate'])} {var} .")
        triples.append(f"  FILTER({var} = {json.dumps(item['value'], ensure_ascii=False)})")
    return "SELECT DISTINCT ?value WHERE {\n" + "\n".join(triples) + "\n}"
