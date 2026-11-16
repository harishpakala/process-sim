"""Single opt-in entry point for experimental SHACL-grounded query planning.

Uses one shared semantic frame, then validated engineering/historian operations.
The engineering path planner is still specialized; this is NOT a fully unified
semantic interpreter. Mixed graph+historian work is not a row-level join.
"""
from __future__ import annotations

import argparse
import json
import os

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.unified_semantic_experimental import plan_unified_question_v3
from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.dtwise.schema import Schema


def run(question, *, schema=None, environ=None, context=None,
        interpret_frame=None, interpret_graph=None, graph_executor=None,
        mapping_executor=None, sample_retriever=None):
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    env = os.environ if environ is None else environ
    if not env.get("GRAPHDB_SPARQL_ENDPOINT"):
        raise ValueError("Configure GRAPHDB_SPARQL_ENDPOINT")
    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    plan = plan_unified_question_v3(
        question.strip(), schema=schema, context=context,
        interpret_frame=interpret_frame, interpret_graph=interpret_graph)
    kinds = tuple(op.kind for op in plan.operations)
    if kinds not in (
        ("graph_query",), ("signal_resolution", "observations"),
        ("graph_query", "signal_resolution", "observations")
    ):
        raise ValueError("Unsupported unified execution sequence")
    if "observations" in kinds and not env.get("TEP_TIMESCALE_DSN"):
        raise ValueError("Configure TEP_TIMESCALE_DSN")
    execution = execute_unified_plan(
        plan, schema, environ=env, single_resolution="observations" in kinds,
        graph_executor=graph_executor, mapping_executor=mapping_executor,
        sample_retriever=sample_retriever)
    return {
        "status": "PASS",
        "mode": "shared_semantic_frame_specialized_shacl_paths_v3",
        "fully_unified_interpretation": False,
        "operation_kinds": kinds,
        "plan": execution["plan"],
        "graph": execution["graph"],
        "historian": execution["historian"],
        "join_type": execution["join_type"],
        "resolution_execution": execution.get("resolution_execution"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--context-json", default=None,
                        help="Optional explicit user-selected domain, identifier, run and bounds")
    args = parser.parse_args()
    context = json.loads(args.context_json) if args.context_json else None
    print(json.dumps(run(args.question, context=context), indent=2, default=str))


if __name__ == "__main__":
    main()
