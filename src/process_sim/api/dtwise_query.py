"""HTTP adapter for direct, in-process DTWise planning and GraphDB execution.

The CLI bridge is intentionally not used by the web API.
"""
from __future__ import annotations

import os
from pathlib import Path

from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import plan_question_semantic
from process_sim.dtwise.sparql_generator import compile_sparql
from process_sim.dtwise.rdf_executor import execute_select, build_answer

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "semantic" / "ontology2" / "dtwise" / "dtwise-schema-index.json"


class DtwiseUnavailable(RuntimeError):
    """DTWise configuration or runtime is unavailable."""


class DtwiseRejected(ValueError):
    """DTWise rejected the requested question."""


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

    try:
        schema = Schema(str(SCHEMA_PATH))
        plan = plan_question_semantic(question, [], schema)
        sparql = compile_sparql(plan, schema, limit=100, graph_mode="all_named")
        bindings = execute_select(endpoint, sparql)
        answer = build_answer(bindings, plan, limit=100)
    except ValueError as exc:
        raise DtwiseRejected(str(exc)) from exc

    return {
        "question": question,
        "mode": "frozen_dtwise_graphdb",
        "graph_mode": "all_named",
        "plan": plan,
        "sparql": sparql,
        "executed": True,
        "answer": answer,
    }
