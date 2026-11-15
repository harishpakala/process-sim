"""Read-only DTwise bridge for process-sim.

Runs the frozen DTwise checkout in-place; no source files are copied or patched.
This is a CLI integration checkpoint, not yet an HTTP endpoint or a TEP join.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def run(question, dtwise_root, schema_path, graphdb_url, *, limit=100,
        execute=False, model="qwen2.5-coder:3b",
        ollama_host="http://localhost:11434"):
    root = Path(dtwise_root).expanduser().resolve()
    schema_file = Path(schema_path).expanduser().resolve()
    if not (root / "dtwise" / "semantic_planner.py").is_file():
        raise ValueError("DTwise root must contain dtwise/semantic_planner.py")
    if not schema_file.is_file():
        raise ValueError("Schema index not found: " + str(schema_file))
    if not question or not question.strip():
        raise ValueError("Question is required")
    if not 1 <= limit <= 5000:
        raise ValueError("Limit must be between 1 and 5000")

    # A single frozen checkout is selected explicitly; do not import from the
    # process-sim working tree or fall back to an unrelated installed package.
    if "dtwise" in sys.modules:
        raise RuntimeError("DTwise already imported; launch a fresh bridge process")
    sys.path.insert(0, str(root))
    from dtwise.schema import Schema
    from dtwise.semantic_planner import plan_question_semantic
    from dtwise.sparql_generator import compile_sparql

    schema = Schema(str(schema_file))
    plan = plan_question_semantic(
        question, [], schema, host=ollama_host, model=model)
    sparql = compile_sparql(plan, schema, limit=limit, graph_mode="all_named")
    result = {
        "question": question,
        "mode": "frozen_dtwise_graphdb",
        "graph_mode": "all_named",
        "plan": plan,
        "sparql": sparql,
        "executed": False,
    }
    if execute:
        from dtwise.rdf_executor import execute_select, build_answer
        bindings = execute_select(graphdb_url, sparql)
        result["answer"] = build_answer(bindings, plan, limit=limit)
        result["executed"] = True
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--question", required=True)
    p.add_argument("--dtwise-root", required=True,
                   help="Directory containing the frozen dtwise/ package")
    p.add_argument("--schema", required=True,
                   help="Exact frozen dtwise-schema-index.json path")
    p.add_argument("--graphdb-url", default=os.environ.get(
        "GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"))
    p.add_argument("--ollama-host", default="http://localhost:11434")
    p.add_argument("--model", default="qwen2.5-coder:3b")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--execute", action="store_true",
                   help="Execute generated read-only SELECT in GraphDB")
    p.add_argument("--output", default=None)
    args = p.parse_args()
    result = run(args.question, args.dtwise_root, args.schema,
                 args.graphdb_url, limit=args.limit, execute=args.execute,
                 model=args.model, ollama_host=args.ollama_host)
    rendered = json.dumps(result, indent=2, default=str)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
