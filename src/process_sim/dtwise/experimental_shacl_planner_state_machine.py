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


class PlannerLifecycle:
    """Shared state and transition contract for planner operations."""

    def __init__(self):
        self.trace = [PlannerState.START]

    def _require(self, state):
        if self.trace[-1] != state:
            raise SelectionContractError(
                f"Expected planner state {state.value}, got {self.trace[-1].value}"
            )

    def _advance(self, target):
        transition(self.trace, target)


class JoinPlannerStateMachine(PlannerLifecycle):
    """One method per stage; transitions occur only after successful gates."""

    def __init__(self, index, prepared, *, model="qwen2.5-coder:7b",
                 endpoint="http://127.0.0.1:11434", transport=None):
        self.index = index
        self.prepared = prepared
        self.model = model
        self.endpoint = endpoint
        self.transport = transport
        super().__init__()
        self.qualified = None
        self.question = None
        self.literals = None
        self.is_or = False
        self.raw = None
        self.plan = None
        self.intent = None
        self.sparql = None

    def qualify(self):
        self._require(PlannerState.START)
        qualified = qualify_candidates(self.index, self.prepared)
        question = qualified["prompt"]["question"]
        self.qualified = qualified
        self.question = question
        self.literals = _literals(question)
        self.is_or = OR_QUESTION.fullmatch(question.strip()) is not None
        self._advance(PlannerState.QUALIFIED)

    def is_supported(self):
        self._require(PlannerState.QUALIFIED)
        return (self.index.domain == "ecad" and self.literals is not None
                and None not in _expected_paths(self.qualified)
                and None not in _filter_ids(self.qualified))

    def select_with_ollama(self):
        self._require(PlannerState.QUALIFIED)
        if not self.is_supported():
            raise SelectionContractError("Unsupported question cannot call Ollama")
        prompt = {**self.qualified["prompt"], "candidates": [
            candidate for candidate in self.qualified["prompt"]["candidates"]
            if candidate["kind"] == "property"
        ]}
        raw = ollama_select(prompt, model=self.model, endpoint=self.endpoint,
                            transport=self.transport,
                            system_prompt=OR_PROMPT if self.is_or else PROMPT)
        self.raw = raw
        self._advance(PlannerState.MODEL_SELECTED)

    def validate(self):
        self._require(PlannerState.MODEL_SELECTED)
        plan = validate_phase4_and_join_plan(self.raw, self.qualified)
        if (plan["status"] == "selected" and
                tuple(item["value"] for item in plan["filters"]) != self.literals):
            raise SelectionContractError("Filter literals do not match question")
        intent = None
        if plan["status"] == "selected" and not self.is_or:
            from process_sim.dtwise.experimental_shacl_query_intent import validated_join_intent
            intent = validated_join_intent(plan, self.qualified)
        self.plan = plan
        self.intent = intent
        self._advance(PlannerState.VALIDATED)

    def compile(self):
        self._require(PlannerState.VALIDATED)
        if self.plan["status"] != "selected":
            raise SelectionContractError("Cannot compile non-selected plan")
        sparql = compile_phase4_and_join_sparql(self._result())
        if sparql is None:
            raise SelectionContractError("Selected plan failed to compile")
        self.sparql = sparql
        self._advance(PlannerState.COMPILED)

    def abstain(self):
        if self.trace[-1] == PlannerState.QUALIFIED:
            self.plan = {
                "status": "unresolved", "result_ids": [],
                "join_owner": None, "filters": [],
                "reason": "Requires verified ECAD shared-Device join with LocalId and DeviceType equality",
            }
        elif self.trace[-1] != PlannerState.VALIDATED or self.plan["status"] == "selected":
            raise SelectionContractError("Abstention requires unsupported or non-selected plan")
        self.sparql = None
        self._advance(PlannerState.ABSTAINED)
        return self._result()

    def _result(self):
        return {
            "domain": self.index.domain, "question": self.question,
            "qualified": self.qualified, "plan": self.plan,
            "intent": self.intent, "sparql": self.sparql,
            "state": self.trace[-1].value,
            "state_trace": [state.value for state in self.trace],
        }

    def run(self):
        self.qualify()
        if not self.is_supported():
            return self.abstain()
        self.select_with_ollama()
        self.validate()
        if self.plan["status"] != "selected":
            return self.abstain()
        self.compile()
        return self._result()


def run_join_state_machine(index, prepared, *, model="qwen2.5-coder:7b",
                           endpoint="http://127.0.0.1:11434", transport=None):
    """Backward-compatible entry point; delegates to per-state methods."""
    return JoinPlannerStateMachine(
        index, prepared, model=model, endpoint=endpoint, transport=transport
    ).run()
