"""Opt-in CLI for existing SHACL-grounded engineering questions.

This is a compatibility baseline for engineering-only questions, not a
general unified NL interpreter. It never calls the historian.
"""
from __future__ import annotations

import argparse
import json
import os

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.api.unified_query_plan import from_engineering_plan
from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import plan_question_semantic


def run(question: str, *, schema=None, environ=None, interpret=None,
        graph_executor=None):
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    question = question.strip()
    env = os.environ if environ is None else environ
    if not env.get("GRAPHDB_SPARQL_ENDPOINT"):
        raise ValueError("Configure GRAPHDB_SPARQL_ENDPOINT")
    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    kwargs = {"interpret": interpret} if interpret is not None else {}
    engineering_plan = plan_question_semantic(question, [], schema, **kwargs)
    unified_plan = from_engineering_plan(question, engineering_plan)
    result = execute_unified_plan(unified_plan, schema, environ=env,
                                  graph_executor=graph_executor)
    if result["historian"] is not None:
        raise RuntimeError("Engineering-only CLI unexpectedly executed historian")
    return {
        "question": question,
        "status": "PASS",
        "mode": "existing_shacl_engineering_planner_via_unified_executor",
        "fully_unified_interpretation": False,
        "plan": result["plan"],
        "sparql": result["graph"]["sparql"],
        "answer": result["graph"]["answer"],
        "historian_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.question), indent=2, default=str))


if __name__ == "__main__":
    main()
