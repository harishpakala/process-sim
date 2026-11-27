"""Restricted execution of lifecycle decision logic.

Reference-bound AAS inputs describe activation dependencies. They are
not Boolean values. Only unbound decision inputs enter the existing
Boolean evaluator; bodies that read AAS values are not supported here.
"""
from dataclasses import replace

from .policy_evaluator import evaluate_policy
from .port_resolution import resolve_port_dependencies


def evaluate_lifecycle_decision(specification, process_name, inputs):
    resolve_port_dependencies(specification)
    matches = [p for p in specification.processes if p.name == process_name]
    if len(matches) != 1:
        raise ValueError("Unknown or ambiguous lifecycle process")
    process = matches[0]
    if any(p.direction == "Output" and p.reference is not None
           for p in process.interface.ports):
        raise ValueError("Bound output Ports are not supported")
    ports = [p for p in process.interface.ports if p.reference is None]
    projected = replace(process, interface=replace(process.interface, ports=ports))
    return evaluate_policy(projected, inputs)
