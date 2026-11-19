"""HTTP adapter for LLM-driven Unified IR DTWise queries and GraphDB execution."""
from __future__ import annotations

import os
from pathlib import Path

from process_sim.dtwise.unified_answer import generate_ir, execute_select
from process_sim.dtwise.graph_compiler import compile_graph_ir

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "semantic" / "ontology2" / "dtwise" / "dtwise-schema-index.json"


class DtwiseUnavailable(RuntimeError):
    """DTWise configuration or runtime is unavailable."""


class DtwiseRejected(ValueError):
    """DTWise rejected the requested question."""


def _binding_value(binding):
    """Decode one SPARQL JSON binding without fabricating missing values."""
    if not isinstance(binding, dict) or "value" not in binding:
        raise ValueError("Malformed GraphDB binding")
    return binding["value"]


def _answer_from_results(results, plan, limit=100):
    """Present Unified IR results using the existing UI answer envelope."""
    bindings = results.get("results", {}).get("bindings", [])
    if not isinstance(bindings, list):
        raise ValueError("Malformed GraphDB results")
    operation = plan["operation"]["type"]
    if operation == "count":
        if len(bindings) != 1 or "count" not in bindings[0]:
            raise ValueError("COUNT result is missing its count binding")
        return {"count": int(_binding_value(bindings[0]["count"])),
                "intent": "count"}

    projections = plan["projections"]
    aliases = [p["as"] for p in projections]
    if len(aliases) == 1:
        name = aliases[0]
        rows = []
        for binding in bindings:
            if name not in binding:
                raise ValueError("Projected property missing from GraphDB result")
            row = {"value": _binding_value(binding[name])}
            if plan["return_entities"]:
                for entity in plan["entities"]:
                    if entity["alias"] in binding:
                        row["entity"] = _binding_value(binding[entity["alias"]])
                        break
            rows.append(row)
        return {"count": len(rows), "values": rows,
                "property": projections[0]["predicate"],
                "projection": "terminal_property",
                "truncated_possible": len(rows) >= limit}

    if aliases:
        rows = []
        for binding in bindings:
            if any(a not in binding for a in aliases):
                raise ValueError("Projected property missing from GraphDB result")
            row = {"properties": {p["predicate"]: _binding_value(binding[p["as"]])
                                   for p in projections}}
            if plan["return_entities"]:
                for entity in plan["entities"]:
                    if entity["alias"] in binding:
                        row["entity"] = _binding_value(binding[entity["alias"]])
                        break
            rows.append(row)
        return {"count": len(rows), "values": rows,
                "properties": [p["predicate"] for p in projections],
                "projection": "multiple_properties",
                "truncated_possible": len(rows) >= limit}

    rows = []
    for binding in bindings:
        for entity in plan["entities"]:
            alias = entity["alias"]
            if alias in binding:
                uri = _binding_value(binding[alias])
                rows.append({"uri": uri, "label": uri.rsplit("/", 1)[-1]})
    return {"count": len(rows), "entities": rows,
            "truncated_possible": len(bindings) >= limit}


def run_question(question: str, *, environ=None):
    env = os.environ if environ is None else environ
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    question = question.strip()
    endpoint = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not endpoint:
        raise DtwiseUnavailable("Configure GRAPHDB_SPARQL_ENDPOINT")
    if not SCHEMA_PATH.is_file():
        raise DtwiseUnavailable("DTWise schema index is unavailable")

    model = env.get("DTWISE_UNIFIED_MODEL", "llama3.1:8b")
    host = env.get("OLLAMA_HOST", "http://localhost:11434")
    try:
        plan = generate_ir(question, str(SCHEMA_PATH), model=model, ollama_host=host)
        sparql = compile_graph_ir(plan, str(SCHEMA_PATH), limit=100,
                                  graph_mode="all_named")
        results = execute_select(sparql, endpoint)
        answer = _answer_from_results(results, plan)
    except ValueError as exc:
        raise DtwiseRejected(str(exc)) from exc

    return {"question": question, "mode": "unified_ir_graphdb",
            "graph_mode": "all_named", "plan": plan, "sparql": sparql,
            "executed": True, "answer": answer}
