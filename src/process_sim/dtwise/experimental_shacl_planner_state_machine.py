"""Explicit, independently executed states for the ECAD two-filter join.

The existing Phase 4 AND/OR entry point remains unchanged. This opt-in
orchestrator reuses its prompts, SHACL checks, validator and compiler.
"""
from enum import Enum

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    PROMPT, OR_PROMPT, OR_QUESTION, _expected_paths, _filter_ids, _literals,
    validate_phase4_and_join_plan, compile_phase4_and_join_sparql,
)
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


class PlannerState(str, Enum):
    START = "start"
    QUALIFIED = "qualified"
    MODEL_SELECTED = "model_selected"
    VALIDATED = "validated"
    COMPILED = "compiled"
    ABSTAINED = "abstained"


ALLOWED_TRANSITIONS = {
    PlannerState.START: {PlannerState.QUALIFIED},
    PlannerState.QUALIFIED: {PlannerState.MODEL_SELECTED, PlannerState.ABSTAINED},
    PlannerState.MODEL_SELECTED: {PlannerState.VALIDATED},
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
    """Qualify -> Ollama -> independently validate -> compile (never execute).

    Unsupported requests abstain before the model call. Contract violations
    raise SelectionContractError, never silently select a fallback plan.
    """
    trace = [PlannerState.START]
    qualified = qualify_candidates(index, prepared)
    transition(trace, PlannerState.QUALIFIED)
    question = qualified["prompt"]["question"]
    literals = _literals(question)
    is_or = OR_QUESTION.fullmatch(question.strip()) is not None

    if (index.domain != "ecad" or literals is None or
            None in _expected_paths(qualified) or None in _filter_ids(qualified)):
        transition(trace, PlannerState.ABSTAINED)
        return {
            "domain": index.domain, "question": question, "qualified": qualified,
            "plan": {"status": "unresolved", "result_ids": [],
                     "join_owner": None, "filters": [],
                     "reason": "Requires verified ECAD shared-Device join with LocalId and DeviceType equality"},
            "intent": None, "sparql": None,
            "state": trace[-1].value,
            "state_trace": [state.value for state in trace],
        }

    prompt = {**qualified["prompt"], "candidates": [
        candidate for candidate in qualified["prompt"]["candidates"]
        if candidate["kind"] == "property"
    ]}
    raw = ollama_select(prompt, model=model, endpoint=endpoint,
                        transport=transport,
                        system_prompt=OR_PROMPT if is_or else PROMPT)
    transition(trace, PlannerState.MODEL_SELECTED)
    plan = validate_phase4_and_join_plan(raw, qualified)
    if (plan["status"] == "selected" and
            tuple(item["value"] for item in plan["filters"]) != literals):
        raise SelectionContractError("Filter literals do not match question")
    transition(trace, PlannerState.VALIDATED)

    intent = None
    if plan["status"] == "selected" and not is_or:
        from process_sim.dtwise.experimental_shacl_query_intent import validated_join_intent
        intent = validated_join_intent(plan, qualified)
    result = {"domain": index.domain, "question": question,
              "plan": plan, "qualified": qualified, "intent": intent}
    if plan["status"] != "selected":
        transition(trace, PlannerState.ABSTAINED)
        sparql = None
    else:
        sparql = compile_phase4_and_join_sparql(result)
        if sparql is None:
            raise SelectionContractError("Selected plan failed to compile")
        transition(trace, PlannerState.COMPILED)
    return {**result, "sparql": sparql, "state": trace[-1].value,
            "state_trace": [state.value for state in trace]}
