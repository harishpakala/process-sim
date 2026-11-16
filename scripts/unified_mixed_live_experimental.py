"""Live, narrow mixed-question acceptance test; not a general NL planner.

Uses a single validated historian plan, one GraphDB entity/signal mapping
request, one SHACL-whitelisted engineering-property request, and TimescaleDB.
No arbitrary SPARQL or SQL is accepted from the question.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from uuid import UUID

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.historian_nl_experimental import _shacl_evidence
from process_sim.api.unified_execution_experimental import execute_unified_plan
from process_sim.api.unified_query_plan import from_historian_plan
from process_sim.dtwise.rdf_executor import execute_select
from process_sim.dtwise.schema import Schema
from process_sim.dtwise.sparql_generator import iri

QUESTION = re.compile(
    r"Show the engineering details of DEXPI InstrumentationFunction "
    r"(?P<function>(?:FI|LI|PI|TI)_[0-9]+) and its recorded measurements "
    r"between simulation seconds (?P<start>[0-9]+(?:\.[0-9]+)?) "
    r"and (?P<end>[0-9]+(?:\.[0-9]+)?) for run "
    r"(?P<run>[0-9a-fA-F-]{36})\.?", re.I)


def parse_question(question):
    match = QUESTION.fullmatch(question.strip())
    if match is None:
        raise ValueError("Only the exact supported DEXPI mixed-question form is accepted")
    return match.group("function").upper(), str(UUID(match.group("run"))), float(
        match.group("start")), float(match.group("end"))


def engineering_details(endpoint, entity, evidence, *, executor=execute_select):
    """Retrieve only engineering predicates present in validated SHACL evidence."""
    predicates = sorted({entry["property"] for entry in evidence["properties"]
                         if isinstance(entry, dict) and isinstance(entry.get("property"), str)})
    if not predicates:
        raise ValueError("No SHACL-verified engineering properties")
    query = ("SELECT DISTINCT ?predicate ?value WHERE {\n"
             " GRAPH ?engineeringGraph {\n"
             f"  {iri(entity)} ?predicate ?value .\n"
             " }\n"
             " VALUES ?predicate { " + " ".join(iri(p) for p in predicates) + " }\n"
             "} ORDER BY ?predicate ?value")
    rows = executor(endpoint, query)
    if not isinstance(rows, list):
        raise ValueError("Invalid engineering detail response")
    permitted = set(predicates)
    if any(not isinstance(row, dict) or set(row) != {"predicate", "value"}
           or row["predicate"] not in permitted or not isinstance(row["value"], str)
           for row in rows):
        raise ValueError("Unexpected engineering detail binding")
    return {"entity": entity, "properties": rows,
            "property_count": len(rows), "sparql": query}


def run(question, *, schema=None, environ=None, detail_executor=execute_select,
        mapping_executor=None, sample_retriever=None):
    env = os.environ if environ is None else environ
    if not env.get("GRAPHDB_SPARQL_ENDPOINT") or not env.get("TEP_TIMESCALE_DSN"):
        raise ValueError("Configure GRAPHDB_SPARQL_ENDPOINT and TEP_TIMESCALE_DSN")
    function, run_id, start, end = parse_question(question)
    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    evidence = _shacl_evidence(schema, "DEXPI")
    plan = from_historian_plan(question, {
        "domain": "DEXPI", "engineering_function": function,
        "run_id": run_id, "start_simulation_seconds": start,
        "end_simulation_seconds": end, "shacl_evidence": evidence})
    result = execute_unified_plan(
        plan, schema, environ=env, single_resolution=True,
        mapping_executor=mapping_executor, sample_retriever=sample_retriever)
    mapping = result["historian"]["mapping"]
    detail = engineering_details(env["GRAPHDB_SPARQL_ENDPOINT"], mapping["entity"],
                                 evidence, executor=detail_executor)
    # Same entity IRI is used for the live mapping and engineering detail query.
    if detail["entity"] != mapping["entity"]:
        raise ValueError("Engineering identity mismatch")
    if not detail["properties"]:
        raise ValueError("No engineering properties found for resolved entity")
    return {"status": "PASS", "question": question,
            "engineering": detail, "historian": result["historian"],
            "execution": {
                "graphdb_mapping_queries": 1,
                "graphdb_engineering_detail_queries": 1,
                "graphdb_total_queries": 2,
                "historian_re_resolved_signal": False,
                "join_type": "shared_resolved_entity_identity_no_row_join"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--require-samples", action="store_true")
    args = parser.parse_args()
    result = run(args.question)
    count = result["historian"]["observationCount"]
    if args.require_samples and count == 0:
        raise RuntimeError("No observations in requested run/window")
    mapping = result["historian"]["mapping"]
    print(json.dumps({
        "status": result["status"], "entity": mapping["entity"],
        "asset_identifier": mapping["asset_identifier"],
        "operational_signal": mapping["operational_signal"],
        "run_id": result["historian"]["runId"],
        "engineering_properties": result["engineering"]["properties"],
        "observation_count": count,
        "graphdb_total_queries": result["execution"]["graphdb_total_queries"],
        "historian_re_resolved_signal": False,
        "physical_sensor_binding": "NOT_VERIFIED",
        "shared_run_provenance": "NOT_VERIFIED",
    }, indent=2))


if __name__ == "__main__":
    main()
