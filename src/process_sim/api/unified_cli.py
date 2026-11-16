"""CLI-only unified Qwen/SHACL planner, GraphDB and TimescaleDB runner.

Examples:
  python -m process_sim.api.unified_cli --question "Show asset identifiers"
  python -m process_sim.api.unified_cli --question "Show signal observations..." \
      --run-id UUID --signal-field signalName

No UI endpoints or legacy NL planners are invoked.
"""
import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path

from process_sim.api.unified_semantic_interpreter import interpret_unified_semantics
from process_sim.api.unified_graph_compiler import (
    compile_unified_graph_query, execute_unified_graph_query,
)
from process_sim.api.unified_historian_executor import execute_unified_historian
from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.dtwise.schema import Schema


def run_unified_cli(question, *, schema, context=None, environ=None,
                    interpret=None, graph_executor=None, connection_factory=None,
                    signal_field=None, dry_run=False):
    """One semantic interpretation; compile/execute only supported operations."""
    env = os.environ if environ is None else environ
    plan = interpret_unified_semantics(question, schema, context=context, interpret=interpret)
    graph_projections = tuple(p for p in plan.projections if p.source == "graphdb")
    has_historian = "timescaledb" in plan.sources
    if has_historian and not graph_projections:
        raise ValueError("Historian requires SHACL-grounded GraphDB signal resolution")
    if has_historian and (not signal_field or signal_field not in {p.name for p in graph_projections}):
        raise ValueError("Select a GraphDB signal projection with --signal-field")
    if not graph_projections:
        raise ValueError("No executable GraphDB projections")
    graph_plan = replace(plan, projections=graph_projections, sources=("graphdb",),
                         run_id=None, start_seconds=None, end_seconds=None,
                         validated=True)
    sparql = compile_unified_graph_query(graph_plan)
    result = {"question": question, "plan": asdict(plan),
              "sparql": sparql, "executed": False}
    if dry_run:
        return result
    endpoint = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not endpoint:
        raise ValueError("Configure GRAPHDB_SPARQL_ENDPOINT")
    graph = execute_unified_graph_query(graph_plan, endpoint, executor=graph_executor)
    result["graph"] = graph
    if has_historian:
        dsn = env.get("TEP_TIMESCALE_DSN")
        if not dsn:
            raise ValueError("Configure TEP_TIMESCALE_DSN")
        # GraphDB has already applied the validated projected-field filter and\n        # ordering. Do not pass those graph-only operations to the historian\n        # executor, which supports run/signal/time filtering but not generic\n        # historian predicates or ordering. Aggregations remain rejected.\n        historian_plan = replace(plan, where=None, order_by=(), validated=True)\n        result["answer"] = execute_unified_historian(\n            historian_plan, dsn, graph_rows=graph["rows"], signal_field=signal_field,
            connection_factory=connection_factory)
    else:
        result["answer"] = {"rows": graph["rows"], "count": graph["count"]}
    result["executed"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument("--signal-field", help="SHACL-grounded GraphDB projection containing operational signal ID")
    parser.add_argument("--dry-run", action="store_true", help="Interpret and compile, without database requests")
    parser.add_argument("--output", help="Optional JSON report file")
    args = parser.parse_args(argv)
    context = {k: v for k, v in {
        "run_id": args.run_id, "start_seconds": args.start_seconds,
        "end_seconds": args.end_seconds}.items() if v is not None}
    report = run_unified_cli(
        args.question, schema=Schema(str(SCHEMA_PATH)), context=context,
        signal_field=args.signal_field, dry_run=args.dry_run)
    serialized = json.dumps(report, indent=2, default=str, allow_nan=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
