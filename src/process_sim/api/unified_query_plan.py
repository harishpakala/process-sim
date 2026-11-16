"""Versioned, backend-neutral query plan contract for the unified planner experiment.

This module defines the common plan representation; semantic interpretation
and cross-source orchestration will be migrated in subsequent increments.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TemporalWindow:
    start_seconds: float | None = None
    end_seconds: float | None = None

    def __post_init__(self) -> None:
        for value in (self.start_seconds, self.end_seconds):
            if value is not None and (not isinstance(value, (int, float)) or
                                      isinstance(value, bool) or not isfinite(value) or value < 0):
                raise ValueError("Simulation time must be finite and nonnegative")
        if (self.start_seconds is not None and self.end_seconds is not None
                and self.start_seconds > self.end_seconds):
            raise ValueError("Start simulation second exceeds end")


@dataclass(frozen=True)
class QueryOperation:
    kind: str
    source: str
    parameters: dict[str, Any] = field(default_factory=dict)
    shacl_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.kind, self.source) not in {
            ("graph_query", "graphdb"),
            ("observations", "timescaledb"),
            ("signal_resolution", "graphdb"),
        }:
            raise ValueError("Unsupported query operation or source")
        if not isinstance(self.parameters, dict) or not isinstance(self.shacl_evidence, dict):
            raise ValueError("Invalid query operation payload")


@dataclass(frozen=True)
class UnifiedQueryPlan:
    question: str
    operations: tuple[QueryOperation, ...]
    temporal: TemporalWindow = field(default_factory=TemporalWindow)
    version: str = "unified-shacl-v1"
    interpretation: str = "legacy_adapter"

    def __post_init__(self) -> None:
        if not isinstance(self.question, str) or not 5 <= len(self.question.strip()) <= 1000:
            raise ValueError("Question must contain 5–1000 characters")
        if not self.operations:
            raise ValueError("Query plan must contain operations")
        if any(op.kind == "observations" for op in self.operations):
            separate_resolution = any(
                op.kind == "signal_resolution" for op in self.operations)
            embedded_resolution = any(
                op.kind == "graph_query"
                and isinstance(op.parameters.get("signal_resolution"), dict)
                and op.parameters["signal_resolution"].get("domain") in ("DEXPI", "ECAD")
                and isinstance(op.parameters["signal_resolution"].get("engineering_function"), str)
                and bool(op.parameters["signal_resolution"]["engineering_function"])
                and isinstance(op.shacl_evidence.get("signal_resolution"), dict)
                and bool(op.shacl_evidence["signal_resolution"].get("properties"))
                and isinstance(op.parameters.get("validated_engineering_plan"), dict)
                and bool(op.parameters["validated_engineering_plan"])
                for op in self.operations)
            if not (separate_resolution or embedded_resolution):
                raise ValueError("Observations require GraphDB signal resolution")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def from_historian_plan(question: str, plan: dict[str, Any]) -> UnifiedQueryPlan:
    """Adapt a SHACL-checked historian plan without fabricating graph paths."""
    domain = plan["domain"]
    function = plan["engineering_function"]
    run_id = str(UUID(plan["run_id"]))
    if domain not in ("DEXPI", "ECAD") or not isinstance(function, str) or not function:
        raise ValueError("Invalid historian entity")
    evidence = plan["shacl_evidence"]
    if not isinstance(evidence, dict) or not evidence.get("properties"):
        raise ValueError("Missing SHACL grounding evidence")
    window = TemporalWindow(plan.get("start_simulation_seconds"),
                            plan.get("end_simulation_seconds"))
    return UnifiedQueryPlan(
        question=question,
        temporal=window,
        operations=(
            QueryOperation("signal_resolution", "graphdb",
                           {"domain": domain, "engineering_function": function},
                           evidence),
            QueryOperation("observations", "timescaledb",
                           {"run_id": run_id, "start_simulation_seconds": window.start_seconds,
                            "end_simulation_seconds": window.end_seconds}),
        ),
    )


def from_engineering_plan(question: str, plan: dict[str, Any]) -> UnifiedQueryPlan:
    """Wrap the existing engineering planner output without weakening its validation."""
    if not isinstance(plan, dict) or not plan:
        raise ValueError("Missing engineering plan")
    return UnifiedQueryPlan(
        question=question,
        operations=(QueryOperation("graph_query", "graphdb",
                                   {"validated_engineering_plan": plan},
                                   {"evidence_ids": plan.get("evidence_ids", [])}),),
    )


def consolidate_graph_stage(plan: UnifiedQueryPlan) -> UnifiedQueryPlan:
    """Represent mixed GraphDB work as one logical graph stage.

    This is a *logical* consolidation only: the existing historian backend
    still performs its own live GraphDB signal lookup. It does not imply a
    single SPARQL request or a verified row-level graph/historian join.
    """
    kinds = tuple(op.kind for op in plan.operations)
    if kinds != ("graph_query", "signal_resolution", "observations"):
        raise ValueError("Expected mixed engineering and historian plan")
    graph, resolution, observations = plan.operations
    if not resolution.shacl_evidence.get("properties"):
        raise ValueError("Signal mapping requires SHACL property evidence")
    if not graph.parameters.get("validated_engineering_plan"):
        raise ValueError("Graph stage requires validated engineering plan")
    combined = QueryOperation(
        kind="graph_query", source="graphdb",
        parameters={**graph.parameters,
                    "signal_resolution": dict(resolution.parameters)},
        shacl_evidence={
            "engineering": dict(graph.shacl_evidence),
            "signal_resolution": dict(resolution.shacl_evidence),
        },
    )
    return UnifiedQueryPlan(
        question=plan.question,
        operations=(combined, observations),
        temporal=plan.temporal,
        interpretation="logical_graph_stage_v5",
    )
