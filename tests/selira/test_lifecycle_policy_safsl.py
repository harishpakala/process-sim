"""Parser compatibility of behavioral LP specifications (not execution)."""
from pathlib import Path

import pytest
from lark import Tree
from process_sim.safsl.ast.nodes import AssignmentNode
from process_sim.safsl.parser.frontend import parse_safsl

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("policy, name, outputs", [
    ("LP-03", "LP_03", {"Affected"}),
    ("LP-04", "LP_04", {"Reassess", "Reuse"}),
])
def test_policy_parses(policy, name, outputs):
    source = (ROOT / "selira_integration/contracts/safsl" / (policy + ".safsl")).read_text(encoding="utf-8")
    spec = parse_safsl(source).children[0]
    assert len(spec.processes) == 1
    process = spec.processes[0]
    assert process.name == name
    assert {p.name for p in process.interface.ports if p.direction == "Output"} == outputs
    def assignments(node):
        if isinstance(node, AssignmentNode):
            yield node
        elif isinstance(node, Tree):
            for child in node.children:
                yield from assignments(child)

    statements = [a for s in process.body.statements for a in assignments(s)]
    assert len(statements) == len(outputs)
    assert {s.target.name for s in statements} == outputs


# Test-only Boolean evaluator for the restricted policy fragment.
# This is not a general SAFSL execution engine.
from itertools import product
from process_sim.safsl.ast.nodes import Identifier, Operation, ExpressionStatement


def evaluate_policy(policy, inputs):
    source = (ROOT / "selira_integration/contracts/safsl" / (policy + ".safsl")).read_text(encoding="utf-8")
    process = parse_safsl(source).children[0].processes[0]
    env = dict(inputs)
    assert set(env) == {p.name for p in process.interface.ports if p.direction == "Input"}
    assert all(type(v) is bool for v in env.values())

    def evaluate(node):
        if isinstance(node, Identifier):
            return env[node.name]
        if isinstance(node, ExpressionStatement):
            return evaluate(node.expression)
        if isinstance(node, Operation):
            args = [evaluate(a) for a in node.operands]
            if node.operator == "and":
                return all(args)
            if node.operator == "or":
                return any(args)
            if node.operator == "notS":
                assert len(args) == 1
                return not args[0]
        raise AssertionError(f"Unsupported expression: {node!r}")

    def execute(node):
        if isinstance(node, Tree) and node.data == "statement":
            assert len(node.children) == 1
            execute(node.children[0])
        elif isinstance(node, AssignmentNode):
            assert node.operator == "assign"
            env[node.target.name] = evaluate(node.value)
        else:
            raise AssertionError(f"Unsupported statement: {node!r}")

    for statement in process.body.statements:
        execute(statement)
    return {p.name: env[p.name] for p in process.interface.ports if p.direction == "Output"}


@pytest.mark.parametrize("bits", list(product([False, True], repeat=6)))
def test_lp03_boolean_decision(bits):
    coverage, policy, authority, assignment, previous, candidate = bits
    inputs = dict(zip(("CoverageAttested", "PolicyUnchanged", "AuthorityUnchanged",
                       "AssignmentChanged", "PreviousLookupChanged", "CandidateLookupChanged"), bits))
    # Reference decision from multi_contract.compare.
    expected = not (coverage and policy and authority) or assignment or previous or candidate
    assert evaluate_policy("LP-03", inputs) == {"Affected": expected}


@pytest.mark.parametrize("bits", list(product([False, True], repeat=4)))
def test_lp04_boolean_decision(bits):
    affected, coverage, policy, authority = bits
    inputs = dict(zip(("Affected", "CoverageAttested", "PolicyUnchanged", "AuthorityUnchanged"), bits))
    # Conservative selection, including independently supplied inconsistent impact flags.
    reuse = coverage and policy and authority and not affected
    assert evaluate_policy("LP-04", inputs) == {"Reassess": not reuse, "Reuse": reuse}
