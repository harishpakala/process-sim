"""Opt-in Phase 3: one result property and exactly two AND equality filters.

Qwen selects verified property IDs; Python checks path ownership and literal
grounding and compiles read-only SPARQL without executing it.
"""
import json
import re

from process_sim.dtwise.experimental_shacl_ollama import ollama_select

from process_sim.dtwise.shacl_planner.operations.phase2_filter import _LITERAL

from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_sparql import _iri

PROMPT = """Plan one or more RETRIEVE results with exactly TWO string equality filters joined by AND.
Use only verified PROPERTY candidate IDs. Do not write SPARQL.
Return ONLY JSON with exactly: status ("selected", "ambiguous", "unresolved"),
result_id (P ID or null), filters (array of two objects each with exactly
filter_id (P ID), owner (string), property (string), operator ("="), 
value (string)), result_meaning (string or null), reason (nonempty string).
For selected status, result_meaning must be the complete owner.property
(e.g. EndPoint.Address), and each filter owner/property must describe
the selected candidate exactly.
For multiple results use result_ids (array of P IDs) and result_meanings
(array of corresponding owner.property strings) INSTEAD of result_id/result_meaning.
If both EndPoint and PLCEndPoint Addresses are requested, select both paths.
For non-selected status use result_id null, result_meaning null and filters [].
Both filter owners must be on the result path, either ancestor or result owner.
Copy literal values exactly from the question and keep their condition order.
No OR, COUNT, EXISTS, numeric comparison, aggregation, cross-branch joins or
cross-branch filter joins. For multiple results, both filters must be
shared ancestors or owners on EVERY result path; compile separate queries.
Abstain if unsupported or ambiguous."""

FIELDS = {"status", "result_id", "result_meaning", "filters", "reason"}
MULTI_FIELDS = {"status", "result_ids", "result_meanings", "filters", "reason"}
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
    if not isinstance(raw, dict) or set(raw) not in (FIELDS, MULTI_FIELDS):
        raise SelectionContractError("Invalid Phase 3 response fields")
    multi = set(raw) == MULTI_FIELDS
    if raw["status"] not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid Phase 3 status")
    if not isinstance(raw["reason"], str) or not raw["reason"].strip():
        raise SelectionContractError("Missing Phase 3 reason")
    if raw["status"] != "selected":
        if multi:
            empty = raw["result_ids"] == [] and raw["result_meanings"] == [] and raw["filters"] == []
        else:
            empty = raw["result_id"] is None and raw["result_meaning"] is None and raw["filters"] == []
        if not empty:
            raise SelectionContractError("Uncertain Phase 3 plan must be empty")
        return raw
    offered = {c["id"] for c in qualified["prompt"]["candidates"]
               if c["kind"] == "property"}
    if multi:
        result_ids = raw["result_ids"]
        meanings = raw["result_meanings"]
        if (not isinstance(result_ids, list) or len(result_ids) < 2 or
                not isinstance(meanings, list) or len(meanings) != len(result_ids) or
                len(set(result_ids)) != len(result_ids)):
            raise SelectionContractError("Invalid multiple result selections")
    else:
        result_ids = [raw["result_id"]]
        meanings = [raw["result_meaning"]]
    if any(rid not in offered for rid in result_ids):
        raise SelectionContractError("Unknown result property ID")
    filters = raw["filters"]
    if not isinstance(filters, list) or len(filters) != 2:
        raise SelectionContractError("Exactly two filters required")
    candidates = {c["id"]: c for c in qualified["prompt"]["candidates"]}
    for rid, meaning in zip(result_ids, meanings):
        result_path = candidates[rid]["path"]
        expected_meaning = ".".join(result_path.split(" → ")[-2:])
        if meaning != expected_meaning:
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
        for rid in result_ids:
            result = qualified["registry"][rid]
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

def _explicit_result_paths(question, qualified):
    """Ground only the supported explicit result wording against full schema paths.

    Do not infer a result from Qwen's proposed IDs or self-reported meanings.
    Unknown phrasing fails closed rather than guessing an output property.
    """
    before_where = re.split(r"\bwhere\b", question, maxsplit=1, flags=re.I)[0].strip()
    match = re.fullmatch(
        r"Show\s+(?P<property>[A-Za-z_][A-Za-z_0-9]*)\s+of\s+"
        r"(?P<owners>both\s+EndPoint\s+and\s+PLCEndPoint|EndPoint|PLCEndPoint)"
        r"\s+belonging\s+to\s+(?P<ancestor>Device)\s*",
        before_where, flags=re.I)
    if match is None:
        return None
    labels = {c["path"] for c in qualified["prompt"]["candidates"]
              if c["kind"] == "property"}
    owners = (["EndPoint", "PLCEndPoint"]
              if match.group("owners").casefold().startswith("both ")
              else [match.group("owners")])
    matches = []
    for owner in owners:
        expected = ["ECAD", match.group("ancestor"), owner, match.group("property")]
        paths = [path for path in labels
                 if [part.casefold() for part in path.split(" → ")] ==
                    [part.casefold() for part in expected]]
        if len(paths) != 1:
            return None
        matches.append(paths[0])
    return matches


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
    result_grounding = _explicit_result_paths(question, qualified) if supported else None
    if grounding is None or result_grounding is None:
        supported = False
    if not supported:
        plan = {"status": "unresolved", "result_id": None, "result_meaning": None, "filters": [],
                "reason": "Requires exactly two AND string equality conditions"}
    else:
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                           transport=transport, system_prompt=PROMPT)
        plan = validate_phase3_plan(raw, qualified)
        if plan["status"] == "selected":
            selected_ids = (plan["result_ids"] if "result_ids" in plan
                            else [plan["result_id"]])
            candidate_paths = {c["id"]: c["path"] for c in
                               qualified["prompt"]["candidates"]}
            if set(candidate_paths[rid] for rid in selected_ids) != set(result_grounding):
                raise SelectionContractError("Result semantic grounding mismatch")
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
    if "result_ids" in plan:
        return {rid: _compile_phase3_one(registry[rid], plan["filters"], registry)
                for rid in plan["result_ids"]}
    return _compile_phase3_one(registry[plan["result_id"]], plan["filters"], registry)


def _compile_phase3_one(selected, filters, registry):
    nodes = selected["node_uris"]
    triples = []
    for i, edge in enumerate(selected["edges"]):
        if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
            raise ValueError("Disconnected result path")
        triples.append(f"  ?n{i} {_iri(edge['predicate'])} ?n{i + 1} .")
    if selected["property"]["owner"] != nodes[-1]:
        raise ValueError("Invalid result property owner")
    triples.append(f"  ?n{len(nodes)-1} {_iri(selected['property']['predicate'])} ?value .")
    for i, item in enumerate(filters, 1):
        filtr = registry[item["filter_id"]]
        if filtr["property"]["owner"] != filtr["node_uris"][-1]:
            raise ValueError("Invalid filter property owner")
        var = f"?filterValue{i}"
        triples.append(f"  ?n{len(filtr['node_uris'])-1} {_iri(filtr['property']['predicate'])} {var} .")
        triples.append(f"  FILTER({var} = {json.dumps(item['value'], ensure_ascii=False)})")
    return "SELECT DISTINCT ?value WHERE {\n" + "\n".join(triples) + "\n}"
