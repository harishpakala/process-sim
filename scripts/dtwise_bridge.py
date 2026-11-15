
"""Read-only DTWise bridge for Process-Sim.

Uses the repository-local process_sim.dtwise package to plan natural-language
questions, compile SPARQL, and optionally execute SELECT queries in GraphDB.
No external DTWise checkout is required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# Allow direct execution:
# python scripts/dtwise_bridge.py ...
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import plan_question_semantic
from process_sim.dtwise.sparql_generator import compile_sparql


def run(
    question,
    schema_path,
    graphdb_url,
    *,
    limit=100,
    execute=False,
    model="qwen2.5-coder:3b",
    ollama_host="http://localhost:11434",
):
    """Plan a question and optionally execute it against GraphDB."""

    schema_file = Path(schema_path).expanduser().resolve()

    if not schema_file.is_file():
        raise ValueError(
            "Schema index not found: " + str(schema_file)
        )

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question is required")

    if not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("Limit must be between 1 and 5000")

    if not graphdb_url:
        raise ValueError("GraphDB SPARQL endpoint is required")

    schema = Schema(str(schema_file))

    # Plan using the repository-local DTWise implementation.
    plan = plan_question_semantic(
        question,
        [],
        schema,
        host=ollama_host,
        model=model,
    )

    # Preserve existing named-graph compilation behavior.
    sparql = compile_sparql(
        plan,
        schema,
        limit=limit,
        graph_mode="all_named",
    )

    result = {
        "question": question,
        "mode": "frozen_dtwise_graphdb",
        "graph_mode": "all_named",
        "plan": plan,
        "sparql": sparql,
        "executed": False,
    }

    if execute:
        from process_sim.dtwise.rdf_executor import (
            execute_select,
            build_answer,
        )

        bindings = execute_select(graphdb_url, sparql)

        result["answer"] = build_answer(
            bindings,
            plan,
            limit=limit,
        )
        result["executed"] = True

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--question",
        required=True,
        help="Natural-language question to answer",
    )

    parser.add_argument(
        "--schema",
        required=True,
        help="Path to the DTWise schema index JSON file",
    )

    parser.add_argument(
        "--graphdb-url",
        default=os.environ.get(
            "GRAPHDB_SPARQL_ENDPOINT",
            "http://localhost:7200/repositories/AAS",
        ),
        help="GraphDB SPARQL repository endpoint",
    )

    parser.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
    )

    parser.add_argument(
        "--model",
        default="qwen2.5-coder:3b",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute generated read-only SELECT in GraphDB",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON file",
    )

    args = parser.parse_args()

    result = run(
        args.question,
        args.schema,
        args.graphdb_url,
        limit=args.limit,
        execute=args.execute,
        model=args.model,
        ollama_host=args.ollama_host,
    )

    rendered = json.dumps(
        result,
        indent=2,
        default=str,
    )

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        output.write_text(
            rendered + "\n",
            encoding="utf-8",
        )

    print(rendered)


if __name__ == "__main__":
    main()
