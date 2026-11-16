"""Opt-in live GraphDB + TimescaleDB smoke check for unified execution.

Run locally with configured GRAPHDB_SPARQL_ENDPOINT and TEP_TIMESCALE_DSN.
Does not use Ollama or change the production API. Does not print credentials
or raw observations.
"""
from __future__ import annotations

import argparse
import json
import os
from uuid import UUID

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.historian_nl_experimental import _shacl_evidence
from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.api.unified_query_plan import from_historian_plan
from process_sim.dtwise.schema import Schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("DEXPI", "ECAD"), required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument("--require-samples", action="store_true",
                        help="Fail if selected run/signal/window has no observations")
    args = parser.parse_args()
    if not os.environ.get("GRAPHDB_SPARQL_ENDPOINT") or not os.environ.get("TEP_TIMESCALE_DSN"):
        parser.error("Configure GRAPHDB_SPARQL_ENDPOINT and TEP_TIMESCALE_DSN")
    schema = Schema(str(SCHEMA_PATH))
    evidence = _shacl_evidence(schema, args.domain)
    run = str(UUID(args.run_id))
    plan = from_historian_plan(
        f"Retrieve recorded measurements for {args.domain} {args.function} in run {run}",
        {"domain": args.domain, "engineering_function": args.function,
         "run_id": run, "start_simulation_seconds": args.start_seconds,
         "end_simulation_seconds": args.end_seconds,
         "shacl_evidence": evidence})
    result = execute_unified_plan(plan, schema, single_resolution=True)
    historian = result["historian"]
    mapping = historian["mapping"]
    observations = historian["observations"]
    if args.require_samples and not observations:
        raise RuntimeError("No observations for resolved signal in selected run/window")
    # All reported values come from live GraphDB and the read-only Timescale query.
    print(json.dumps({
        "status": "PASS",
        "domain": args.domain,
        "engineering_function": mapping["engineering_function"],
        "entity": mapping["entity"],
        "asset_identifier": mapping["asset_identifier"],
        "operational_signal": mapping["operational_signal"],
        "run_id": historian["runId"],
        "observation_count": historian["observationCount"],
        "graphdb_signal_resolution_queries": result["resolution_execution"]["graphdb_signal_resolution_queries"],
        "historian_re_resolved_signal": result["resolution_execution"]["historian_re_resolved_signal"],
        "physical_sensor_binding": mapping["physical_sensor_binding"],
        "shared_run_provenance": historian["provenance"]["sharedRunProvenance"],
        "engineering_graph_query_executed": result["graph"] is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
