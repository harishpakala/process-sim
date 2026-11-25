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


from itertools import product
from process_sim.selira.reassessment.policy import load_policy, evaluate_policy as execute_policy


def evaluate_policy(policy, inputs):
    return execute_policy(load_policy(ROOT / "selira_integration/contracts/safsl" / (policy + ".safsl")), inputs)


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
