"""Isolated NL-to-VTKG historian experiment. Existing endpoints remain unchanged.

This prototype accepts an explicit domain, LocalID, run UUID and optional
simulation-second bounds in the question. It refuses to guess missing fields.
"""
from __future__ import annotations

import re
from uuid import UUID

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.dtwise.schema import Schema
from process_sim.api.vtkg_query import run_historian_question

_LOCAL_ID = re.compile(r"(?<![A-Za-z0-9_-])(?:FI|LI|PI|TI)[_-][0-9]+(?![A-Za-z0-9_-])", re.I)
_UUID = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}(?![a-fA-F0-9])")
_RANGE = re.compile(r"\bbetween\s+(?:simulation\s+)?(?:seconds?\s+)?(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\s*(?:seconds?)?\b", re.I)
_FROM = re.compile(r"\bfrom\s+(?:simulation\s+)?seconds?\s+(\d+(?:\.\d+)?)\s+onward\b", re.I)
_UPTO = re.compile(r"\bup\s+to\s+(?:simulation\s+)?seconds?\s+(\d+(?:\.\d+)?)\b", re.I)


def _shacl_evidence(schema: Schema, domain: str) -> dict:
    """Ground domain and engineering identifier properties in the schema index."""
    target = "instrumentationfunction" if domain == "DEXPI" else "device"
    shapes = [c for c in schema.concepts if c.get("kind") == "shape"
              and str(c.get("domain", "")).casefold() == domain.casefold()
              and any(target in str(label).casefold().replace(" ", "")
                      for label in c.get("labels", []))]
    if not shapes:
        raise ValueError(f"No SHACL shape for {domain} {target}")
    evidence = []
    for shape in shapes:
        for chain in schema.shacl_paths(shape["uri"], max_depth=1, domain=domain.lower()):
            hop = chain[0]
            if hop.get("to_shape") is not None:
                continue
            property_uri = hop["property"]
            concept = schema.by_uri.get(property_uri, {})
            labels = [str(v) for v in concept.get("labels", [])]
            normalized = " ".join(labels + [property_uri]).casefold().replace(" ", "")
            if "localid" in normalized or "assetidentifier" in normalized:
                evidence.append({"property": property_uri, "evidence_ids": hop["evidence_ids"]})
    if not any("localid" in str(x["property"]).casefold() or
               "localid" in " ".join(schema.by_uri.get(x["property"], {}).get("labels", [])).casefold().replace(" ", "")
               for x in evidence):
        raise ValueError(f"SHACL LocalID evidence unavailable for {domain}")
    return {"shape": shapes[0]["uri"], "properties": evidence}


def plan_historian_question(question: str, *, schema: Schema | None = None, context: dict | None = None) -> dict:
    """Normalize supported paraphrases, then validate against SHACL evidence.

    Context is explicitly user-selected; conflicting text is never silently overridden.
    """
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    q = question.strip()
    context = {} if context is None else context
    allowed = {"domain", "engineering_function", "run_id", "start_simulation_seconds", "end_simulation_seconds"}
    if not isinstance(context, dict) or set(context) - allowed:
        raise ValueError("Invalid historian query context")
    if not re.search(r"\\b(historian|history|historical|recorded|readings?|values?|measurements?|observations?|samples?|trends?|plot|chart|graph|time.series|behav(?:e|ior|iour))\\b", q, re.I):
        raise ValueError("Question does not request historian observations")

    domains = [d for d in ("DEXPI", "ECAD") if re.search(r"\\b" + d + r"\\b", q, re.I)]
    if len(domains) > 1:
        raise ValueError("Ambiguous engineering domain")
    domain = domains[0] if domains else context.get("domain")
    if domain not in ("DEXPI", "ECAD") or (domains and context.get("domain") not in (None, domain)):
        raise ValueError("Specify one consistent engineering domain: DEXPI or ECAD")

    ids = {v.upper() for v in _LOCAL_ID.findall(q)}
    selected_id = context.get("engineering_function")
    if selected_id is not None and (not isinstance(selected_id, str) or not _LOCAL_ID.fullmatch(selected_id)):
        raise ValueError("Invalid selected LocalID")
    if len(ids) > 1 or (ids and selected_id and ids != {selected_id.upper()}):
        raise ValueError("Question and selected LocalID disagree")
    function = next(iter(ids)) if ids else selected_id.upper() if selected_id else None
    if not function:
        raise ValueError("Specify exactly one engineering LocalID")

    runs = {str(UUID(v)) for v in _UUID.findall(q)}
    try:
        selected_run = str(UUID(str(context["run_id"]))) if context.get("run_id") else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid selected run UUID") from exc
    if len(runs) > 1 or (runs and selected_run and runs != {selected_run}):
        raise ValueError("Question and selected run disagree")
    run_id = next(iter(runs)) if runs else selected_run
    if not run_id:
        raise ValueError("Specify exactly one simulation run UUID")

    start = end = None
    interval = re.search(r"\\b(?:between|from)\\s+(?:simulation\\s+)?(?:seconds?\\s+)?(\\d+(?:\\.\\d+)?)\\s+(?:and|to|through|until)\\s+(\\d+(?:\\.\\d+)?)\\s*(?:seconds?)?\\b", q, re.I)
    if interval:
        start, end = float(interval[1]), float(interval[2])
    elif match := re.search(r"\\bfrom\\s+(?:simulation\\s+)?seconds?\\s+(\\d+(?:\\.\\d+)?)\\s+onward\\b", q, re.I):
        start = float(match[1])
    elif match := re.search(r"\\bup\\s+to\\s+(?:simulation\\s+)?seconds?\\s+(\\d+(?:\\.\\d+)?)\\b", q, re.I):
        end = float(match[1])
    elif re.search(r"\\b(between|from|until|before|after|last|first|since)\\b", q, re.I):
        raise ValueError("Unsupported or incomplete time interval; specify simulation seconds")
    for field, value in (("start_simulation_seconds", start), ("end_simulation_seconds", end)):
        selected = context.get(field)
        if selected is not None:
            selected = float(selected)
            if value is not None and value != selected:
                raise ValueError("Question and selected time interval disagree")
            if field == "start_simulation_seconds":
                start = selected
            else:
                end = selected
    if (start is not None and not 0 <= start < float("inf")) or (end is not None and not 0 <= end < float("inf")):
        raise ValueError("Simulation seconds must be finite and nonnegative")
    if start is not None and end is not None and start > end:
        raise ValueError("Start simulation second must not exceed end")

    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    evidence = _shacl_evidence(schema, domain)
    return {"intent": "historian_observations", "domain": domain,
            "engineering_function": function, "run_id": run_id,
            "start_simulation_seconds": start, "end_simulation_seconds": end,
            "shacl_evidence": evidence}

def run_historian_nl_experiment(question: str, *, environ=None, context=None) -> dict:
    plan = plan_historian_question(question, context=context)
    payload = {key: plan[key] for key in ("domain", "engineering_function", "run_id",
               "start_simulation_seconds", "end_simulation_seconds")}
    payload["question"] = question.strip()
    result = run_historian_question(payload, environ=environ)
    return {"mode": "historian_nl_experimental", "plan": plan, "result": result}
