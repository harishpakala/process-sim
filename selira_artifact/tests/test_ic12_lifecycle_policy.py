from pathlib import Path

import pytest

from selira.language.parser.frontend import parse_safsl
from selira.runtime.lifecycle_policy import evaluate_lifecycle_decision
from selira.runtime.port_resolution import resolve_port_dependencies

SOURCE = (Path(__file__).resolve().parents[1] / "policies" / "LP-01.safsl").read_text(encoding="utf-8")


def specification(source=SOURCE):
    return parse_safsl(source).children[0]


def test_ic12_lp01_interface():
    spec = specification()
    process = spec.processes[0]
    assert process.name == "LP_01"
    assert [(t.direction, t.name) for t in process.interface.terminals] == [
        ("Input", "START"), ("Output", "DONE")]
    assert [(d.port, d.template_id) for d in resolve_port_dependencies(spec)] == [
        ("Assets", "https://example.org/sm/asset-inventory-template"),
        ("Products", "https://example.org/sm/product-catalog-template")]


@pytest.mark.parametrize("changed", [True, False])
def test_ic12_lp01_decision(changed):
    assert evaluate_lifecycle_decision(specification(), "LP_01",
                                       {"ChangeDetected": changed}) == {"Reassess": changed}


@pytest.mark.parametrize("inputs", [{}, {"ChangeDetected": 1},
                                    {"ChangeDetected": True, "Assets": True}])
def test_ic12_lp01_invalid_inputs(inputs):
    with pytest.raises(ValueError):
        evaluate_lifecycle_decision(specification(), "LP_01", inputs)


def test_ic12_lp01_unknown_process():
    with pytest.raises(ValueError):
        evaluate_lifecycle_decision(specification(), "Unknown", {"ChangeDetected": True})


def test_ic12_lp01_unsupported_aas_read():
    spec = specification(SOURCE.replace("assign(Reassess, ChangeDetected)",
                                        "assign(Reassess, Assets)"))
    with pytest.raises(KeyError):
        evaluate_lifecycle_decision(spec, "LP_01", {"ChangeDetected": True})
