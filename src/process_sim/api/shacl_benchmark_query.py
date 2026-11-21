"""Live, read-only Phase-1 SHACL benchmark execution for Engineering Queries."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "benchmarks/shacl_phase1/benchmark_queries_aast_candidate.json"
SCHEMA = ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json"
MAPPINGS = ROOT / "semantic/ontology2/dtwise/cross-domain-mappings.json"
GRAPHS = ROOT / "benchmarks/shacl_phase1/aast_instance_graphs.json"


def run_benchmark_question(variant_id: str, question: str | None = None) -> dict:
    if not isinstance(variant_id, str) or len(variant_id) > 32:
        raise ValueError("Invalid benchmark question ID")
    scenarios = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    match = next(((s, p) for s in scenarios for p in s["paraphrases"]
                  if p["id"] == variant_id), None)
    if match is None:
        raise ValueError("Unknown SHACL benchmark question ID")
    scenario, variant = match
    if question is None:
        question = variant["query"]
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5 to 1000 characters")
    question = question.strip()
    sid = scenario["scenario_id"]
    domains = scenario["expected_semantics"]["domains"]
    base = {"id": variant_id, "scenario_id": sid, "question": question,
            "domains": domains, "status": "planning_failed", "sparql": None,
            "row_count": None, "columns": [], "rows": [], "mapping_ids": [],
            "error": None, "plan": None}
    from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
    from process_sim.dtwise.shacl_planner.sparql_compiler import (
        CompilationError, compile_single_domain,
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        indices = {domain: load_index(SCHEMA, domain=domain) for domain in domains}
        if sid.startswith("SD"):
            from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one
            record = run_one(indices[domains[0]], question, method="expanded",
                             model=os.getenv("SHACL_PLANNER_MODEL", "qwen2.5-coder:7b"),
                             endpoint=os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434"))
        else:
            from process_sim.dtwise.shacl_planner.cross_domain_phase1 import run_cross_domain
            record = run_cross_domain(
                indices, question, mapping_file=MAPPINGS, method="expanded",
                model=os.getenv("SHACL_PLANNER_MODEL", "qwen2.5-coder:7b"),
                endpoint=os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434"))
    except Exception as exc:
        return {**base, "error": f"{type(exc).__name__}: {exc}"}
    base["plan"] = record.get("answer")
    base["mapping_ids"] = (record.get("answer") or {}).get("mapping_ids") or []
    if record.get("status") != "valid_response" or record.get("validation_errors"):
        return {**base, "error": record.get("validation_errors") or
                record.get("error") or record.get("status")}
    try:
        if sid.startswith("SD"):
            sparql = compile_single_domain(record, indices[domains[0]], schema)
        else:
            from process_sim.dtwise.shacl_planner.cross_domain_sparql_compiler import compile_cross_domain
            sparql = compile_cross_domain(record, indices, schema,
                                          json.loads(GRAPHS.read_text(encoding="utf-8")),
                                          json.loads(MAPPINGS.read_text(encoding="utf-8")))
    except (CompilationError, KeyError, TypeError, ValueError, OSError) as exc:
        return {**base, "status": "compilation_failed",
                "error": f"{type(exc).__name__}: {exc}"}
    base["sparql"] = sparql
    if not isinstance(sparql, str) or not sparql.lstrip().upper().startswith("SELECT"):
        return {**base, "status": "compilation_failed", "error": "Only SELECT is permitted"}
    endpoint = os.getenv("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAST")
    try:
        request = Request(endpoint, data=urlencode({"query": sparql}).encode("utf-8"),
                          headers={"Accept": "application/sparql-results+json",
                                   "Content-Type": "application/x-www-form-urlencoded"},
                          method="POST")
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
        columns = payload["head"]["vars"]
        bindings = payload["results"]["bindings"]
        if not isinstance(columns, list) or not isinstance(bindings, list):
            raise ValueError("Invalid SPARQL JSON results")
        rows = [{key: binding[key].get("value") for key in columns if key in binding}
                for binding in bindings]
        return {**base, "status": "executed_with_results" if rows else "executed_zero_rows",
                "row_count": len(rows), "columns": columns, "rows": rows}
    except Exception as exc:
        return {**base, "status": "execution_failed",
                "error": f"{type(exc).__name__}: {exc}"}
