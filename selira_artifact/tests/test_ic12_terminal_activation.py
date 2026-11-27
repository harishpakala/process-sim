from pathlib import Path

import pytest

from selira.language.parser.frontend import parse_safsl
from selira.runtime.aas_messages import PolicyIntent
from selira.runtime.terminal_activation import activate_policies

SOURCE = (Path(__file__).resolve().parents[1] / "policies" / "LP-01.safsl").read_text(encoding="utf-8")
ASSETS = "https://example.org/sm/asset-inventory-template"
PRODUCTS = "https://example.org/sm/product-catalog-template"


def spec(source=SOURCE):
    return parse_safsl(source).children[0]


def activate(source=SOURCE, template=ASSETS, intent=None):
    return activate_policies({"LP-01": spec(source)}, template_id=template,
                             candidate=object(), intent=intent)


@pytest.mark.parametrize("template,port", [(ASSETS, "Assets"), (PRODUCTS, "Products")])
def test_ic12_automatic_activation(template, port):
    trace, = activate(template=template)
    assert (trace.policy_id, trace.process, trace.matched_ports) == ("LP-01", "LP_01", (port,))
    assert (trace.start_terminal, trace.done_terminal, trace.reassess) == ("START", "DONE", True)


def test_ic12_unrelated():
    assert activate(template="urn:unrelated") == ()


@pytest.mark.parametrize("terminal", [None, "START"])
def test_ic12_explicit_activation(terminal):
    assert activate(intent=PolicyIntent(policy_id="LP-01", activation_terminal=terminal)) == activate()


@pytest.mark.parametrize("policy,terminal,template", [
    ("unknown", "START", ASSETS), ("LP-01", "DONE", ASSETS),
    ("LP-01", "START", "urn:unrelated")])
def test_ic12_invalid_intent(policy, terminal, template):
    with pytest.raises(ValueError):
        activate(template=template, intent=PolicyIntent(policy_id=policy, activation_terminal=terminal))


def test_ic12_multiple_ports_one_execution():
    trace, = activate(SOURCE.replace("Port Input Products = ProductCatalog;",
                                     "Port Input Products = AssetInventory;"))
    assert trace.matched_ports == ("Assets", "Products")


@pytest.mark.parametrize("source", [
    SOURCE.replace("StartTerminal=[LP_01]", "StartTerminal=[Unknown]"),
    SOURCE.replace("Terminal Input START", "Terminal Input OTHER"),
    SOURCE.replace("Terminal Output DONE", "Terminal Output OTHER"),
    SOURCE.replace("assign(Reassess, ChangeDetected)", "assign(Reassess, notS(ChangeDetected))"),
])
def test_ic12_invalid_activation_configuration(source):
    with pytest.raises(ValueError):
        activate(source)


def test_ic12_explicit_does_not_suppress_other_policies():
    traces = activate_policies({"LP-01": spec(), "LP-other": spec()},
                               template_id=ASSETS, candidate=object(),
                               intent=PolicyIntent(policy_id="LP-01"))
    assert [t.policy_id for t in traces] == ["LP-01", "LP-other"]
