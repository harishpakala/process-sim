"""IC-09B: finite differential checks against explicit expected violations."""
import itertools
import json
from pathlib import Path
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SH
from pyshacl import validate
from selira.compiler.shacl import compile_contract
from selira.formal.reference_evaluator import evaluate

ROOT = Path(__file__).resolve().parents[2] / "selira_integration/contracts"
LOCAL = [(), ("FI_101",), ("fi_101",), ("SC_101",), ("FI_101", "FI101")]
ASSET = [(), ("FI101",), ("M1",), ("FI101", "M1")]

@pytest.mark.parametrize("number,domain", [("02", "dexpi"), ("03", "ecad")])
def test_bounded_identifier_compiler(number, domain):
    source = (ROOT / "safsl" / f"SC-{number}.safsl").read_text()
    bindings = json.loads((ROOT / "bindings" / f"SC-{number}.json").read_text())
    ttl, _ = compile_contract(source, bindings)
    shapes = Graph().parse(data=ttl, format="turtle")
    left = URIRef(f"https://example.org/{domain}/hasLocalId")
    right = URIRef(f"https://example.org/{domain}/hasAssetIdentifier")
    cases = 0
    for local, asset in itertools.product(LOCAL, ASSET):
        g = Graph()
        node, control = URIRef("urn:bounded:node"), URIRef("urn:bounded:control")
        for v in local:
            g.add((node, left, Literal(v)))
        for v in asset:
            g.add((node, right, URIRef("https://aas.example.com/" + v)))
        g.add((control, left, Literal("CV-1006")))
        g.add((control, right, URIRef("https://aas.example.com/CV1006")))
        valid = (local == ("FI_101",) and asset == ("FI101",)) or (
            number == "02" and local == ("SC_101",) and asset == ("M1",))
        expected = {str(node)} if asset and not valid else set()
        rows = evaluate(source, bindings, g)[f"SC_{number}"]
        assert set(rows) == {str(control)} | ({str(node)} if asset else set())
        assert {n for n, row in rows.items() if not row["conforms"]} == expected
        conforms, report, _ = validate(g, shacl_graph=shapes, inference="none", advanced=False)
        assert bool(conforms) == (not expected)
        assert {str(n) for n in report.objects(None, SH.focusNode)} == expected
        cases += 1
    assert cases == 20
