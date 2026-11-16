"""Experimental shared semantic planning entry point (planning only).

The same schema instance and typed contract are used for graph and observation
questions. This is a transitional planner: historian extraction still uses the
legacy constrained parser, so it is NOT yet a single Qwen interpretation model.
No production endpoint is changed.
"""
from __future__ import annotations

import re

from process_sim.api.dtwise_query import SCHEMA_PATH
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
    question: str, *, context: dict | None = None, schema: Schema | None = None
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
    if _OBSERVATION_TERMS.search(question):
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
        if _TEMPORAL_TERMS.search(question):
            raise ValueError("Temporal question lacks a supported observation intent")
        graph_plan = plan_question_semantic(question, [], schema)
        result = from_engineering_plan(question, graph_plan)
    return UnifiedQueryPlan(
        question=result.question,
        operations=result.operations,
        temporal=result.temporal,
        interpretation="shared_schema_transitional_v1",
    )
