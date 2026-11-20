"""Explicit state transitions for the verified ECAD two-filter join pipeline.

This is an additive orchestration layer. It does not infer intent, select
properties, bypass Ollama, or execute SPARQL. Existing planners remain intact.
"""
from dataclasses import dataclass
from enum import Enum

from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    compile_phase4_and_join_sparql,
    run_phase4_and_join_plan,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


class PlannerState(str, Enum):
    START = "start"
    QUALIFIED = "qualified"
    MODEL_SELECTED = "model_selected"
    VALIDATED = "validated"
    COMPILED = "compiled"
    ABSTAINED = "abstained"


@dataclass(frozen=True)
class PlannerTransition:
    source: PlannerState
    target: PlannerState


ALLOWED_TRANSITIONS = {
    PlannerState.START: {PlannerState.QUALIFIED, PlannerState.ABSTAINED},
    PlannerState.QUALIFIED: {PlannerState.MODEL_SELECTED, PlannerState.ABSTAINED},
    PlannerState.MODEL_SELECTED: {PlannerState.VALIDATED, PlannerState.ABSTAINED},
    PlannerState.VALIDATED: {PlannerState.COMPILED, PlannerState.ABSTAINED},
    PlannerState.COMPILED: set(),
    PlannerState.ABSTAINED: set(),
}


def transition(trace, target):
    source = trace[-1]
    if target not in ALLOWED_TRANSITIONS[source]:
        raise SelectionContractError(
            f"Invalid planner state transition: {source.value} -> {target.value}"
        )
    trace.append(target)


def run_join_state_machine(index, prepared, *, model="qwen2.5-coder:7b",
                           endpoint="http://127.0.0.1:11434", transport=None):
    """Run existing live selection/validation; expose state without changing semantics.

    The existing planner currently combines qualification, model selection, and
    validation in one function. The state trace records successful gates, not
    independent timing or a claim that each gate is separately invoked here.
    """
    trace = [PlannerState.START]
    result = run_phase4_and_join_plan(
        index, prepared, model=model, endpoint=endpoint, transport=transport
    )
    transition(trace, PlannerState.QUALIFIED)
    if result["plan"]["status"] != "selected":
        transition(trace, PlannerState.ABSTAINED)
        return {**result, "sparql": None, "state": trace[-1].value,
                "state_trace": [state.value for state in trace]}
    transition(trace, PlannerState.MODEL_SELECTED)
    transition(trace, PlannerState.VALIDATED)
    sparql = compile_phase4_and_join_sparql(result)
    if sparql is None:
        raise SelectionContractError("Selected plan failed to compile")
    transition(trace, PlannerState.COMPILED)
    return {**result, "sparql": sparql, "state": trace[-1].value,
            "state_trace": [state.value for state in trace]}
