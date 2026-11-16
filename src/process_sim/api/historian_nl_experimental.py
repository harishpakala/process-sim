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
_UUID = re.compile(r"(?<![a-fA-F0-9])(?:[a-fA-F0-9]{8}-){4}[a-fA-F0-9]{12}(?![a-fA-F0-9])")
_RANGE = re.compile(r"\\bbetween\\s+(?:simulation\\s+)?(?:seconds?\\s+)?(\\d+(?:\\.\\d+)?)\\s+and\\s+(\\d+(?:\\.\\d+)?)\\s*(?:seconds?)?\\b", re.I)
_FROM = re.compile(r"\\bfrom\\s+(?:simulation\\s+)?seconds?\\s+(\\d+(?:\\.\\d+)?)\\s+onward\\b", re.I)
_UPTO = re.compile(r"\\bup\\s+to\\s+(?:simulation\\s+)?seconds?\\s+(\\d+(?:\\.\\d+)?)\\b", re.I)


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


def plan_historian_question(question: str, *, schema: Schema | None = None) -> dict:
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    q = question.strip()
    if not re.search(r"\\b(historian|historical|recorded|time.series|observations?)\\b", q, re.I):
        raise ValueError("Question does not request historian observations")
    domains = [name for name in ("DEXPI", "ECAD") if re.search(r"\\b" + name + r"\\b", q, re.I)]
    if len(domains) != 1:
        raise ValueError("Specify exactly one engineering domain: DEXPI or ECAD")
    ids = {v.upper() for v in _LOCAL_ID.findall(q)}
    if len(ids) != 1:
        raise ValueError("Specify exactly one engineering LocalID")
    runs = {str(UUID(v)) for v in _UUID.findall(q)}
    if len(runs) != 1:
        raise ValueError("Specify exactly one simulation run UUID")
    start = end = None
    matched = _RANGE.search(q)
    if matched:
        start, end = float(matched[1]), float(matched[2])
    elif matched := _FROM.search(q):
        start = float(matched[1])
    elif matched := _UPTO.search(q):
        end = float(matched[1])
    elif re.search(r"\\b(between|from|until|before|after|last|first)\\b", q, re.I) and not re.search(r"\\ball (?:simulation )?times\\b", q, re.I):
        raise ValueError("Unsupported or incomplete time interval; use 'between simulation seconds X and Y'")
    if start is not None and end is not None and start > end:
        raise ValueError("Start simulation second must not exceed end")
    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    evidence = _shacl_evidence(schema, domains[0])
    return {"intent": "historian_observations", "domain": domains[0],
            "engineering_function": next(iter(ids)), "run_id": next(iter(runs)),
            "start_simulation_seconds": start, "end_simulation_seconds": end,
            "shacl_evidence": evidence}


def run_historian_nl_experiment(question: str, *, environ=None) -> dict:
    plan = plan_historian_question(question)
    payload = {key: plan[key] for key in ("domain", "engineering_function", "run_id",
               "start_simulation_seconds", "end_simulation_seconds")}
    payload["question"] = question.strip()
    result = run_historian_question(payload, environ=environ)
    return {"mode": "historian_nl_experimental", "plan": plan, "result": result}
