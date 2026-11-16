"""Experimental shared semantic planning entry point (planning only).

One Qwen-assisted, SHACL-catalog-grounded intent selector is shared across
both question classes. Detailed historian extraction still uses the legacy
constrained parser, so interpretation is NOT yet fully unified.
No production endpoint is changed.
"""
from __future__ import annotations

import re

from process_sim.api.dtwise_query import SCHEMA_PATH
from process_sim.api.unified_intent_selector import select_semantic_intent
from process_sim.api.historian_nl_experimental import plan_historian_question
from process_sim.api.unified_query_plan import (
    UnifiedQueryPlan, from_engineering_plan, from_historian_plan,
)
from process_sim.dtwise.schema import Schema
from process_sim.dtwise.semantic_planner import plan_question_semantic

_OBSERVATION_TERMS = re.compile(
    r"\b(historian|history|historical|recorded|readings?|measurements?|"
    r"observations?|samples?|trends?|plot|chart|time.series)\b", re.I
)
_TEMPORAL_TERMS = re.compile(
    r"\b(simulation\s+run|simulation\s+seconds?|during\s+(?:the\s+)?run)\b", re.I
)


def plan_unified_question(
    question: str, *, context: dict | None = None, schema: Schema | None = None,
    interpret_intent=None
) -> UnifiedQueryPlan:
    """Produce the common plan without executing GraphDB or TimescaleDB.

    Ambiguous observation/graph combinations fail closed instead of silently
    dropping a requested graph relationship. Cross-source joins are not yet
    supported by this increment.
    """
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    if context is not None and not isinstance(context, dict):
        raise ValueError("Context must be a dictionary")
    question = question.strip()
    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    intent = select_semantic_intent(question, schema, interpret=interpret_intent)
    if intent == "mixed":
        raise ValueError("Mixed graph and observation queries are not yet supported")
    if intent == "observations":
        # A question that explicitly asks for an engineering relationship as
        # well as observations must not be reduced to observations alone.
        if re.search(
            r"\b(which|what)\s+(?:equipment|devices?|assets?|components?)\b"
            r"|\b(associated with|connected to|belongs? to)\b",
            question, re.I,
        ):
            raise ValueError("Mixed graph and observation queries are not yet supported")
        legacy = plan_historian_question(question, schema=schema, context=context)
        result = from_historian_plan(question, legacy)
    else:
        # Context is a hint, never permission to silently switch to historian.
        graph_plan = plan_question_semantic(question, [], schema)
        result = from_engineering_plan(question, graph_plan)
    return UnifiedQueryPlan(
        question=result.question,
        operations=result.operations,
        temporal=result.temporal,
        interpretation="qwen_shared_intent_specialized_details_v2",
    )


def plan_unified_question_v3(question: str, *, context=None, schema=None,
                             interpret_frame=None, interpret_graph=None):
    """Opt-in one-pass semantic frame planning; no execution or API migration.

    Historical details no longer use the legacy regex historian planner.
    Engineering graph paths still use the established SHACL/Qwen planner.
    Mixed questions produce a combined plan only if the engineering graph\n    planner also succeeds. Execution and cross-source joins are not implemented.
    """
    from process_sim.api.unified_semantic_frame import interpret_semantic_frame
    from process_sim.api.historian_nl_experimental import _shacl_evidence

    schema = schema if schema is not None else Schema(str(SCHEMA_PATH))
    frame = interpret_semantic_frame(question, schema, context=context,
                                     interpret=interpret_frame)
    if frame.intent in ("observations", "mixed"):
        evidence = _shacl_evidence(schema, frame.domain)
        legacy_shape = {
            "domain": frame.domain, "engineering_function": frame.local_id,
            "run_id": frame.run_id,
            "start_simulation_seconds": frame.temporal.start_seconds,
            "end_simulation_seconds": frame.temporal.end_seconds,
            "shacl_evidence": evidence,
        }
        result = from_historian_plan(question, legacy_shape)
        if frame.intent == "mixed":
            # Graph planning is independent of observation execution. A mixed
            # question is never downgraded to observations if graph grounding
            # fails. The graph planner must validate the requested path.
            options = {"interpret": interpret_graph} if interpret_graph is not None else {}
            graph_plan = plan_question_semantic(question, [], schema, **options)
            graph_result = from_engineering_plan(question, graph_plan)
            result = UnifiedQueryPlan(
                question=question,
                operations=graph_result.operations + result.operations,
                temporal=frame.temporal,
                interpretation="single_semantic_frame_mixed_plan_v4",
            )
    else:
        options = {"interpret": interpret_graph} if interpret_graph is not None else {}
        graph_plan = plan_question_semantic(question, [], schema, **options)
        result = from_engineering_plan(question, graph_plan)
    return UnifiedQueryPlan(
        question=result.question, operations=result.operations,
        temporal=result.temporal,
        interpretation=result.interpretation if frame.intent == "mixed" else "single_semantic_frame_v3",
    )
