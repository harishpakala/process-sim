"""Opt-in read-only execution of validated unified query plans.

The graph query uses the existing SHACL SPARQL compiler. Historian retrieval
uses the existing GraphDB->TimescaleDB resolver/executor. Results remain
separate with shared identity metadata; this is not a row-level semantic join.
"""
from __future__ import annotations

from process_sim.api.historian_nl_experimental import canonical_historian_question
from process_sim.api.unified_query_plan import UnifiedQueryPlan, QueryOperation
from process_sim.api.vtkg_query import run_historian_question
from process_sim.dtwise.rdf_executor import build_answer, execute_select
from process_sim.dtwise.sparql_generator import compile_sparql
from process_sim.api.unified_graph_resolution_experimental import resolve_entity_signal


def execute_unified_plan(plan: UnifiedQueryPlan, schema, *, environ=None,
                         graph_executor=None, historian_executor=None,
                         single_resolution=False, mapping_executor=None,
                         sample_retriever=None):
    """Execute validated operations; optionally reuse one live mapping for samples."""
    import os
    env = os.environ if environ is None else environ
    if not isinstance(plan, UnifiedQueryPlan):
        raise ValueError("Expected a validated unified query plan")
    logical_plan = plan
    kinds = tuple(op.kind for op in plan.operations)
    if kinds == ("graph_query", "observations"):
        graph, observations = plan.operations
        resolution = graph.parameters.get("signal_resolution")
        evidence = graph.shacl_evidence.get("signal_resolution")
        if not isinstance(resolution, dict) or not isinstance(evidence, dict):
            raise ValueError("Combined graph stage lacks signal resolution grounding")
        plan = UnifiedQueryPlan(
            question=plan.question, temporal=plan.temporal,
            operations=(
                QueryOperation("graph_query", "graphdb",
                               {"validated_engineering_plan":
                                graph.parameters.get("validated_engineering_plan")},
                               graph.shacl_evidence.get("engineering", {})),
                QueryOperation("signal_resolution", "graphdb", resolution, evidence),
                observations,
            ),
            interpretation=plan.interpretation,
        )
        kinds = tuple(op.kind for op in plan.operations)
    allowed = (
        ("graph_query",),
        ("signal_resolution", "observations"),
        ("graph_query", "signal_resolution", "observations"),
    )
    if kinds not in allowed:
        raise ValueError("Unsupported unified execution sequence")
    graph_op = next((op for op in plan.operations if op.kind == "graph_query"), None)
    signal_op = next((op for op in plan.operations if op.kind == "signal_resolution"), None)
    observation_op = next((op for op in plan.operations if op.kind == "observations"), None)
    endpoint = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not endpoint:
        raise ValueError("Configure GRAPHDB_SPARQL_ENDPOINT")
    if observation_op is not None and not env.get("TEP_TIMESCALE_DSN"):
        raise ValueError("Configure TEP_TIMESCALE_DSN")
    if single_resolution and historian_executor is not None:
        raise ValueError("single_resolution cannot use the legacy historian executor")
    # Validate the complete plan and required parameters before any I/O.
    if graph_op is not None:
        graph_plan = graph_op.parameters.get("validated_engineering_plan")
        if not isinstance(graph_plan, dict) or not graph_plan:
            raise ValueError("Missing validated engineering graph plan")
        sparql = compile_sparql(graph_plan, schema, limit=100, graph_mode="all_named")
    if signal_op is not None:
        domain = signal_op.parameters.get("domain")
        function = signal_op.parameters.get("engineering_function")
        run_id = observation_op.parameters.get("run_id")
        if domain not in ("DEXPI", "ECAD") or not isinstance(function, str) or not function:
            raise ValueError("Invalid signal-resolution entity")
        if not signal_op.shacl_evidence.get("properties"):
            raise ValueError("Missing signal-resolution SHACL evidence")
        from uuid import UUID
        run_id = str(UUID(str(run_id)))
        if (observation_op.parameters.get("start_simulation_seconds") != plan.temporal.start_seconds
                or observation_op.parameters.get("end_simulation_seconds") != plan.temporal.end_seconds):
            raise ValueError("Observation bounds disagree with unified plan")
        historian_plan = {
            "domain": domain, "engineering_function": function, "run_id": run_id,
            "start_simulation_seconds": plan.temporal.start_seconds,
            "end_simulation_seconds": plan.temporal.end_seconds,
        }
        payload = {**historian_plan,
                   "question": canonical_historian_question(historian_plan)}
    result = {"question": plan.question, "interpretation": plan.interpretation,
              "plan": logical_plan.to_dict(), "graph": None, "historian": None,
              "join_type": "shared_entity_context_no_row_join"}
    if graph_op is not None:
        bindings = (graph_executor or execute_select)(endpoint, sparql)
        result["graph"] = {"sparql": sparql, "answer": build_answer(
            bindings, graph_plan, limit=100)}
    if observation_op is not None:
        if single_resolution:
            if historian_executor is not None:
                raise ValueError("single_resolution cannot use the legacy historian executor")
            from pathlib import Path
            import sys
            from process_sim.api.vtkg_query import ROOT
            # The existing read-only parameterized retriever is reused directly.
            # Unlike run_historian_question, it does not resolve the signal again.
            if sample_retriever is None:
                scripts = str(ROOT / "scripts")
                sys.path.insert(0, scripts)
                try:
                    from tep_nexus_dexpi_historian import retrieve
                    sample_retriever = retrieve
                finally:
                    sys.path.remove(scripts)
            resolver_kwargs = {"evidence": signal_op.shacl_evidence}
            if mapping_executor is not None:
                resolver_kwargs["executor"] = mapping_executor
            mapping = resolve_entity_signal(
                endpoint, domain, function, **resolver_kwargs)
            samples = sample_retriever(
                env["TEP_TIMESCALE_DSN"], run_id, mapping["operational_signal"],
                plan.temporal.start_seconds, plan.temporal.end_seconds)
            if not isinstance(samples, list):
                raise ValueError("Invalid historian observation result")
            result["historian"] = {
                "domain": domain, "engineeringFunction": function,
                "runId": run_id, "mapping": mapping,
                "observations": samples, "observationCount": len(samples),
                "timeBasis": "simulation_time",
                "startSimulationSeconds": plan.temporal.start_seconds,
                "endSimulationSeconds": plan.temporal.end_seconds,
                "materializedInGraphDB": False,
                "provenance": {
                    "semanticSource": "live GraphDB engineering/OPCUA mapping",
                    "temporalSource": "TimescaleDB public.signal_samples",
                    "physicalSensorBinding": "NOT_VERIFIED",
                    "sharedRunProvenance": "NOT_VERIFIED",
                },
            }
            result["resolution_execution"] = {
                "graphdb_signal_resolution_queries": 1,
                "historian_re_resolved_signal": False,
                "additional_engineering_query": graph_op is not None,
            }
        else:
            historian = historian_executor or run_historian_question
            result["historian"] = historian(payload, environ=env)
    if logical_plan is not plan:
        result["graph_stage"] = {
            "logical_consolidation": True,
            "single_sparql_request": False,
            "mapping_validation": ("single_live_entity_signal_select" if single_resolution
                                   else "existing_live_historian_resolver"),
        }
    return result
