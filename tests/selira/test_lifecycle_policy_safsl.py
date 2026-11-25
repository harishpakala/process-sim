"""Parser compatibility of behavioral LP specifications (not execution)."""
from pathlib import Path

import pytest
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
    assert {s.target.name for s in process.body.statements} == outputs
