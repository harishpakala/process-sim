"""Explicit, independently executed states for the ECAD two-filter join.

The existing Phase 4 AND/OR entry point remains unchanged. This opt-in
orchestrator reuses its prompts, SHACL checks, validator and compiler.
"""
from enum import Enum
import re
from time import perf_counter

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.shacl_planner.operations.phase4_and_join import (
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

    def _timed(self, name, action):
        if getattr(self, "timing", None) is None:
            return action()
        t0 = perf_counter()
        try:
            return action()
        finally:
            self.timing[name] = (perf_counter() - t0) * 1000

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
                 endpoint="http://127.0.0.1:11434", transport=None, timing=None):
        self.index = index
        self.prepared = prepared
        self.model = model
        self.endpoint = endpoint
        self.transport = transport
        self.timing = timing
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
                            system_prompt=OR_PROMPT if self.is_or else PROMPT,
                            timing=self.timing)
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
            from process_sim.dtwise.shacl_planner.planning.query_intent import validated_join_intent
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
        self._timed("candidate_qualification_ms", self.qualify)
        if not self.is_supported():
            return self.abstain()
        self._timed("qwen_selection_ms", self.select_with_ollama)
        self._timed("python_validation_ms", self.validate)
        if self.plan["status"] != "selected":
            return self.abstain()
        self._timed("sparql_compilation_ms", self.compile)
        return self._result()


def run_join_state_machine(index, prepared, *, model="qwen2.5-coder:7b",
                           endpoint="http://127.0.0.1:11434", transport=None, timing=None):
    """Backward-compatible entry point; delegates to per-state methods."""
    return JoinPlannerStateMachine(
        index, prepared, model=model, endpoint=endpoint, transport=transport,
        timing=timing
    ).run()


class RetrievePlannerStateMachine(PlannerLifecycle):
    """RETRIEVE stages, preserving Phase 1 selection and verified auto-joins.

    This entry point is not wired to the CLI until parity is verified.
    """

    def __init__(self, index, prepared, *, model="qwen2.5-coder:7b",
                 endpoint="http://127.0.0.1:11434", transport=None, timing=None):
        super().__init__()
        self.index, self.prepared = index, prepared
        self.model, self.endpoint, self.transport = model, endpoint, transport
        self.timing = timing
        self.qualified = None
        self.question = None
        self.properties = None
        self.offered = None
        self.unsupported = False
        self.raw = None
        self.selection = None
        self.auto_join_groups = []
        self.queries = []

    def qualify(self):
        self._require(PlannerState.START)
        t0 = perf_counter()
        qualified = qualify_candidates(self.index, self.prepared)
        properties = [c for c in qualified["prompt"]["candidates"]
                      if c["kind"] == "property"]
        question = qualified["prompt"]["question"]
        offered = {
            "prompt": {**qualified["prompt"], "candidates": properties},
            "registry": {c["id"]: qualified["registry"][c["id"]] for c in properties},
        }
        unsupported = bool(re.search(
            r"\b(how many|count|does (?:any|a|an)|is there|are there|"
            r"average|sum|minimum|maximum|sort|order by|group by)\b",
            question, re.I,
        )) or bool(re.search(
            r"\b[A-Za-z_][A-Za-z_0-9]*\s*(?:=|!=|<=|>=|<|>)\s*[\"'0-9]",
            question,
        ))
        self.qualified, self.properties, self.question = qualified, properties, question
        self.offered, self.unsupported = offered, unsupported
        if self.timing is not None:
            self.timing["candidate_qualification_ms"] = (perf_counter() - t0) * 1000
        self._advance(PlannerState.QUALIFIED)
        return qualified

    def is_supported(self):
        self._require(PlannerState.QUALIFIED)
        return not self.unsupported and bool(self.properties)

    def select_with_ollama(self):
        self._require(PlannerState.QUALIFIED)
        if not self.is_supported():
            raise SelectionContractError("Unsupported RETRIEVE cannot call Ollama")
        from process_sim.dtwise.shacl_planner.operations.phase1_ollama import PHASE1_SYSTEM_PROMPT
        t0 = perf_counter()
        raw = ollama_select(self.offered["prompt"], model=self.model,
                            endpoint=self.endpoint, transport=self.transport,
                            system_prompt=PHASE1_SYSTEM_PROMPT,
                            timing=self.timing)
        self.raw = raw
        if self.timing is not None:
            self.timing["qwen_selection_ms"] = (perf_counter() - t0) * 1000
        self._advance(PlannerState.MODEL_SELECTED)

    def validate(self):
        self._require(PlannerState.MODEL_SELECTED)
        from process_sim.dtwise.experimental_shacl_selection import validate_selection
        from process_sim.dtwise.experimental_shacl_join_topology import verified_shared_ancestor
        t0 = perf_counter()
        selection = validate_selection(self.raw, self.offered)
        groups = []
        bare_request = re.fullmatch(
            r"(?:show|find|list)\s+(?:the\s+)?([A-Za-z_][A-Za-z_0-9]*)"
            r"(?:\s+in\s+[A-Za-z_][A-Za-z_0-9]*)?\s*[.!]?\s*",
            self.question, flags=re.I,
        )
        if bare_request:
            property_name = bare_request.group(1).casefold()
            matches = [c for c in self.properties
                       if c.get("property_name", "").casefold() == property_name]
            by_parent = {}
            for candidate in matches:
                nodes = self.qualified["registry"][candidate["id"]]["node_uris"]
                if len(nodes) >= 2:
                    by_parent.setdefault(nodes[-2], []).append(candidate["id"])
            possible = [ids for ids in by_parent.values() if len(ids) == 2]
            if len(matches) > 1 and sum(map(len, possible)) == len(matches):
                try:
                    for ids in possible:
                        topology = verified_shared_ancestor(self.qualified, ids)
                        if topology["ancestor_uri"] != self.qualified["registry"][ids[0]]["node_uris"][-2]:
                            raise SelectionContractError("Join is not at immediate parent")
                except SelectionContractError:
                    pass
                else:
                    groups = possible
                    selection = {
                        "status": "selected",
                        "selected_candidate_ids": [rid for ids in groups for rid in ids],
                        "reason": "Automatic joins within verified shared-parent groups",
                    }
            if len(matches) > 1 and not groups:
                selection = {
                    "status": "ambiguous", "selected_candidate_ids": [],
                    "reason": "Multiple property paths without fully verified sibling join groups",
                }
        self.selection, self.auto_join_groups = selection, groups
        if self.timing is not None:
            self.timing["python_validation_ms"] = (perf_counter() - t0) * 1000
        self._advance(PlannerState.VALIDATED)

    def compile(self):
        self._require(PlannerState.VALIDATED)
        if self.selection["status"] != "selected":
            raise SelectionContractError("Cannot compile non-selected RETRIEVE")
        from process_sim.dtwise.shacl_planner.operations.phase1_ollama import compile_phase1_sparql
        queries = compile_phase1_sparql(self._result())
        if not queries:
            raise SelectionContractError("Selected RETRIEVE produced no SPARQL")
        self.queries = queries
        self._advance(PlannerState.COMPILED)
        return queries

    def abstain(self):
        if self.trace[-1] == PlannerState.QUALIFIED:
            self.selection = {
                "status": "unresolved", "selected_candidate_ids": [],
                "reason": ("Unsupported operation or filter in RETRIEVE-only Phase 1"
                           if self.unsupported else "No verified SHACL property candidates"),
            }
        elif self.trace[-1] != PlannerState.VALIDATED or self.selection["status"] == "selected":
            raise SelectionContractError("Abstention requires unsupported or non-selected RETRIEVE")
        self.queries = []
        self._advance(PlannerState.ABSTAINED)
        return self._result()

    def _result(self):
        selection = self.selection
        selected = [
            {"id": c["id"], "domain": c["domain"], "kind": c["kind"], "path": c["path"]}
            for c in self.properties if c["id"] in selection["selected_candidate_ids"]
        ]
        groups = self.auto_join_groups
        return {
            "domain": self.index.domain, "question": self.question,
            "plan": {**selection, "operation": "RETRIEVE" if selection["status"] == "selected" else None},
            "selected_paths": selected, "qualified": self.qualified,
            "auto_join_result_ids": groups[0] if len(groups) == 1 else [],
            "auto_join_groups": groups,
            "queries": self.queries,
            "state": self.trace[-1].value,
            "state_trace": [state.value for state in self.trace],
        }

    def run(self, *, compile_sparql=True):
        self.qualify()
        if not self.is_supported():
            result = self.abstain()
        else:
            self.select_with_ollama()
            self.validate()
            if self.selection["status"] != "selected":
                result = self.abstain()
            else:
                if compile_sparql:
                    self.compile()
                result = self._result()
        if self.timing is not None:
            self.timing.setdefault("qwen_selection_ms", 0.0)
            self.timing.setdefault("python_validation_ms", 0.0)
        return result


def run_retrieve_state_machine(index, prepared, *, model="qwen2.5-coder:7b",
                               endpoint="http://127.0.0.1:11434",
                               transport=None, timing=None, compile_sparql=True):
    """Opt-in RETRIEVE state machine; not yet connected to the CLI."""
    return RetrievePlannerStateMachine(
        index, prepared, model=model, endpoint=endpoint,
        transport=transport, timing=timing,
    ).run(compile_sparql=compile_sparql)


class FilterAndJoinStateMachine(PlannerLifecycle):
    """Independent stages for the remaining single-domain operations.

    Existing operation-specific validators and compilers remain authoritative.
    Unsupported requests abstain before model selection.
    """

    OPERATIONS = ("phase2-filter", "phase3-and", "phase4-join", "phase4-filtered-join")

    def __init__(self, index, prepared, *, operation, model="qwen2.5-coder:7b",
                 endpoint="http://127.0.0.1:11434", transport=None):
        super().__init__()
        if operation not in self.OPERATIONS:
            raise ValueError(f"Unsupported state-machine operation: {operation}")
        self.index, self.prepared, self.operation = index, prepared, operation
        self.model, self.endpoint, self.transport = model, endpoint, transport
        self.timing = timing
        self.qualified = self.question = self.prompt = self.raw = self.plan = None
        self.literal = self.literals = self.constraints = self.result_paths = None
        self.supported = False
        self.sparql = None

    def qualify(self):
        self._require(PlannerState.START)
        from process_sim.dtwise.shacl_planner.operations import phase2_filter as p2
        from process_sim.dtwise.shacl_planner.operations import phase3_and as p3
        from process_sim.dtwise.shacl_planner.operations import phase4_join as p4
        from process_sim.dtwise.shacl_planner.operations import phase4_filtered_join as p42
        qualified = qualify_candidates(self.index, self.prepared)
        question = qualified["prompt"]["question"]
        prompt = {**qualified["prompt"], "candidates": [
            c for c in qualified["prompt"]["candidates"] if c["kind"] == "property"
        ]}
        supported = bool(prompt["candidates"])
        if self.operation == "phase2-filter":
            literals = [quoted if quoted != "" else unquoted
                        for quoted, unquoted in p2._LITERAL.findall(question)]
            clause = re.split(r"\bwhere\b", question, maxsplit=1, flags=re.I)[-1]
            supported = supported and len(literals) == 1 and not re.search(
                r"\b(how many|count|exists|does any|is there|are there|average|sum|"
                r"group by|order by|greater than|less than)\b|(?:!=|<=|>=|<|>)",
                question, re.I,
            ) and not re.search(r"\b(and|or)\b", clause, re.I)
            self.literals = literals
        elif self.operation == "phase3-and":
            parts = re.split(r"\bwhere\b", question, maxsplit=1, flags=re.I)
            clause = parts[1] if len(parts) == 2 else ""
            literals = [quoted if quoted != "" else unquoted
                        for quoted, unquoted in p2._LITERAL.findall(clause)]
            supported = (supported and len(literals) == 2
                         and len(re.findall(r"\band\b", clause, re.I)) == 1
                         and not re.search(r"\bor\b", clause, re.I)
                         and not p3.UNSUPPORTED.search(question))
            self.constraints = p3._explicit_filter_constraints(clause, qualified) if supported else None
            self.result_paths = p3._explicit_result_paths(question, qualified) if supported else None
            supported = supported and self.constraints is not None and self.result_paths is not None
            self.literals = literals
        elif self.operation == "phase4-join":
            supported = (supported and self.index.domain == "ecad"
                         and p4.QUESTION.fullmatch(question.strip()) is not None
                         and None not in p4._expected_paths(qualified))
        else:
            match = p42.QUESTION.fullmatch(question.strip())
            supported = (supported and self.index.domain == "ecad" and match is not None
                         and None not in p42._expected_paths(qualified)
                         and p42._filter_id(qualified) is not None)
            if match is not None:
                self.literal = next(v for v in match.group("double", "single", "bare")
                                    if v is not None)
        self.qualified, self.question, self.prompt = qualified, question, prompt
        self.supported = bool(supported)
        self._advance(PlannerState.QUALIFIED)

    def is_supported(self):
        self._require(PlannerState.QUALIFIED)
        return self.supported

    def select_with_ollama(self):
        self._require(PlannerState.QUALIFIED)
        if not self.supported:
            raise SelectionContractError("Unsupported operation cannot call Ollama")
        from process_sim.dtwise.shacl_planner.operations import phase2_filter as p2
        from process_sim.dtwise.shacl_planner.operations import phase3_and as p3
        from process_sim.dtwise.shacl_planner.operations import phase4_join as p4
        from process_sim.dtwise.shacl_planner.operations import phase4_filtered_join as p42
        prompts = {"phase2-filter": p2.PROMPT, "phase3-and": p3.PROMPT,
                   "phase4-join": p4.PROMPT, "phase4-filtered-join": p42.PROMPT}
        self.raw = ollama_select(self.prompt, model=self.model,
                                endpoint=self.endpoint, transport=self.transport,
                                system_prompt=prompts[self.operation],
                                timing=self.timing)
        self._advance(PlannerState.MODEL_SELECTED)

    def validate(self):
        self._require(PlannerState.MODEL_SELECTED)
        from process_sim.dtwise.shacl_planner.operations import phase2_filter as p2
        from process_sim.dtwise.shacl_planner.operations import phase3_and as p3
        from process_sim.dtwise.shacl_planner.operations import phase4_join as p4
        from process_sim.dtwise.shacl_planner.operations import phase4_filtered_join as p42
        validators = {"phase2-filter": p2.validate_filter_plan,
                      "phase3-and": p3.validate_phase3_plan,
                      "phase4-join": p4.validate_phase4_join_plan,
                      "phase4-filtered-join": p42.validate_phase4_filtered_join_plan}
        plan = validators[self.operation](self.raw, self.qualified)
        if plan["status"] == "selected":
            if self.operation == "phase2-filter":
                # Preserve the existing explicit-owner safeguard.
                result_clause = re.split(r"\bwhere\b", self.question, maxsplit=1, flags=re.I)[0]
                owners = {
                    cid: next((c["path"].split(" → ")[-2]
                               for c in self.prompt["candidates"] if c["id"] == cid), "")
                    for cid in plan["result_ids"]
                }
                mentioned = {owner.casefold() for owner in owners.values()
                             if owner and re.search(
                                 r"(?<![A-Za-z_0-9])" + re.escape(owner) + r"(?![A-Za-z_0-9])",
                                 result_clause, re.I)}
                if len(mentioned) == 1:
                    owner = next(iter(mentioned))
                    kept = [cid for cid in plan["result_ids"]
                            if owners[cid].casefold() == owner]
                    if kept and len(kept) != len(plan["result_ids"]):
                        plan = {**plan, "result_ids": kept,
                                "reason": "Explicit result owner excludes unrequested sibling paths"}
                if plan["value"] != self.literals[0]:
                    raise SelectionContractError("Filter value does not match question literal")
            elif self.operation == "phase3-and":
                ids = plan["result_ids"] if "result_ids" in plan else [plan["result_id"]]
                paths = {c["id"]: c["path"] for c in self.qualified["prompt"]["candidates"]}
                if {paths[rid] for rid in ids} != set(self.result_paths):
                    raise SelectionContractError("Result semantic grounding mismatch")
                if [item["value"] for item in plan["filters"]] != self.literals:
                    raise SelectionContractError("Filter values do not match question literals")
                for item, (owner, prop, value) in zip(plan["filters"], self.constraints):
                    if (item["owner"].casefold(), item["property"].casefold(), item["value"]) != (
                            owner.casefold(), prop.casefold(), value):
                        raise SelectionContractError("Filter semantic grounding mismatch")
            elif self.operation == "phase4-filtered-join" and plan["value"] != self.literal:
                raise SelectionContractError("Filter value does not match question literal")
        self.plan = plan
        self._advance(PlannerState.VALIDATED)

    def compile(self):
        self._require(PlannerState.VALIDATED)
        if self.plan["status"] != "selected":
            raise SelectionContractError("Cannot compile non-selected plan")
        from process_sim.dtwise.shacl_planner.operations import phase2_filter as p2
        from process_sim.dtwise.shacl_planner.operations import phase3_and as p3
        from process_sim.dtwise.shacl_planner.operations import phase4_join as p4
        from process_sim.dtwise.shacl_planner.operations import phase4_filtered_join as p42
        compilers = {"phase2-filter": p2.compile_phase2_filter_sparql,
                     "phase3-and": p3.compile_phase3_and_sparql,
                     "phase4-join": p4.compile_phase4_join_sparql,
                     "phase4-filtered-join": p42.compile_phase4_filtered_join_sparql}
        compiled = compilers[self.operation](self._result())
        if not compiled:
            raise SelectionContractError("Selected plan failed to compile")
        self.sparql = compiled
        self._advance(PlannerState.COMPILED)

    def abstain(self):
        if self.trace[-1] == PlannerState.QUALIFIED:
            from process_sim.dtwise.shacl_planner.operations import phase2_filter as p2
            from process_sim.dtwise.shacl_planner.operations import phase3_and as p3
            from process_sim.dtwise.shacl_planner.operations import phase4_join as p4
            from process_sim.dtwise.shacl_planner.operations import phase4_filtered_join as p42
            if self.operation == "phase2-filter":
                self.plan = {"status": "unresolved", "result_ids": [], "filter_id": None,
                             "operator": None, "value": None,
                             "reason": "Unsupported or missing single string equality filter/candidates"}
            elif self.operation == "phase3-and":
                self.plan = {"status": "unresolved", "result_id": None,
                             "result_meaning": None, "filters": [],
                             "reason": "Requires exactly two AND string equality conditions"}
            elif self.operation == "phase4-join":
                self.plan = {"status": "unresolved", "result_ids": [], "join_owner": None,
                             "reason": "Requires two explicit ECAD Address paths joined on the same Device"}
            else:
                self.plan = {"status": "unresolved", "result_ids": [], "join_owner": None,
                             "filter_id": None, "filter_owner": None,
                             "filter_property": None, "operator": None, "value": None,
                             "reason": "Requires explicit same-Device ECAD Address join with one Device.LocalId equality"}
        elif self.trace[-1] != PlannerState.VALIDATED or self.plan["status"] == "selected":
            raise SelectionContractError("Abstention requires unsupported or non-selected plan")
        self._advance(PlannerState.ABSTAINED)
        return self._result()

    def _result(self):
        result = {"domain": self.index.domain, "question": self.question,
                  "plan": self.plan, "qualified": self.qualified,
                  "state": self.trace[-1].value,
                  "state_trace": [state.value for state in self.trace]}
        if self.operation in ("phase2-filter",):
            result["queries"] = self.sparql if self.sparql is not None else []
        else:
            result["sparql"] = self.sparql
        return result

    def run(self):
        self._timed("candidate_qualification_ms", self.qualify)
        if not self.is_supported():
            return self.abstain()
        self._timed("qwen_selection_ms", self.select_with_ollama)
        self._timed("python_validation_ms", self.validate)
        if self.plan["status"] != "selected":
            return self.abstain()
        self._timed("sparql_compilation_ms", self.compile)
        return self._result()


def run_single_domain_state_machine(index, prepared, *, operation,
                                    model="qwen2.5-coder:7b",
                                    endpoint="http://127.0.0.1:11434",
                                    transport=None, timing=None,
                                    compile_sparql=True):
    """Common explicit dispatcher; model still selects operation-specific IDs."""
    if operation == "phase1-plan":
        return run_retrieve_state_machine(
            index, prepared, model=model, endpoint=endpoint,
            transport=transport, timing=timing, compile_sparql=compile_sparql)
    if operation == "phase4-and-join":
        return run_join_state_machine(
            index, prepared, model=model, endpoint=endpoint, transport=transport, timing=timing)
    return FilterAndJoinStateMachine(
        index, prepared, operation=operation, model=model,
        endpoint=endpoint, transport=transport, timing=timing).run()
