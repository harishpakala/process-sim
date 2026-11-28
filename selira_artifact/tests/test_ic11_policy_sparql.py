from itertools import product
from pathlib import Path
import pytest

from selira.compiler.policy_sparql import compile_policy, execute_compiled
from selira.runtime.policy_evaluator import load_policy, evaluate_policy

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("policy", ["LP-03", "LP-04"])
@pytest.mark.parametrize("bits", list(product([False, True], repeat=4)))
def test_backend_equivalence(policy, bits):
    process = load_policy(ROOT / "policies" / (policy + ".safsl"))
    compiled = compile_policy(process)
    inputs = dict(zip(compiled["inputs"], bits))
    assert execute_compiled(compiled, inputs) == evaluate_policy(process, inputs)


@pytest.mark.parametrize("inputs", [{}, {"x": True}])
def test_invalid_inputs(inputs):
    compiled = compile_policy(load_policy(ROOT / "policies" / "LP-03.safsl"))
    with pytest.raises(ValueError):
        execute_compiled(compiled, inputs)
