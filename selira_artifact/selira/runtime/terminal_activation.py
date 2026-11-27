"""Synchronous activation of the supported single-entry lifecycle processes."""
from dataclasses import dataclass

from .port_resolution import resolve_port_dependencies, affected_ports
from .lifecycle_policy import evaluate_lifecycle_decision


@dataclass(frozen=True)
class ActivationTrace:
    policy_id: str
    process: str
    matched_ports: tuple[str, ...]
    start_terminal: str
    done_terminal: str
    reassess: bool


def activate_policies(policies, *, template_id, candidate, intent=None):
    """Policies maps trusted registry IDs to parsed specifications.

    An explicit intent can confirm a compatible activation but cannot
    suppress other matching policies. No persistence or admission occurs.
    """
    planned = []
    for policy_id, spec in policies.items():
        deps = resolve_port_dependencies(spec)
        matched = affected_ports(deps, template_id=template_id, candidate=candidate)
        if not matched:
            continue
        if len(spec.processes) != 1:
            raise ValueError("Only single-process lifecycle policies are supported")
        process = spec.processes[0]
        if spec.start_terminal is None or spec.start_terminal.terminals != [process.name]:
            raise ValueError("Invalid StartTerminal process reference")
        inputs = [t.name for t in process.interface.terminals if t.direction == "Input"]
        outputs = [t.name for t in process.interface.terminals if t.direction == "Output"]
        if inputs != ["START"] or outputs != ["DONE"]:
            raise ValueError("Expected START and DONE Terminals")
        planned.append((policy_id, spec, process, matched))

    if intent is not None:
        if not any(policy_id == intent.policy_id for policy_id, _, _, _ in planned):
            raise ValueError("Explicit policy is unknown or incompatible with affected Ports")
        if intent.activation_terminal not in (None, "START"):
            raise ValueError("Invalid explicit activation Terminal")

    traces = []
    for policy_id, spec, process, matched in planned:
        result = evaluate_lifecycle_decision(spec, process.name, {"ChangeDetected": True})
        if set(result) != {"Reassess"} or result["Reassess"] is not True:
            raise ValueError("Matched lifecycle policy must request reassessment")
        traces.append(ActivationTrace(policy_id, process.name,
                                      tuple(d.port for d in matched),
                                      "START", "DONE", result["Reassess"]))
    return tuple(traces)
