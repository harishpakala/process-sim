"""Exercise the actual migrated integration contracts."""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SH
from pyshacl import validate
from selira.compiler.shacl import compile_contract
from selira.formal.reference_evaluator import evaluate

ROOT = Path(__file__).resolve().parents[2] / "selira_integration" / "contracts"

@pytest.mark.parametrize("number,domain,exception", [
    ("02", "dexpi", True), ("03", "ecad", False),
])
def test_migrated_identifier_contract(number, domain, exception):
    source = (ROOT / "safsl" / f"SC-{number}.safsl").read_text()
    bindings = json.loads((ROOT / "bindings" / f"SC-{number}.json").read_text())
    ttl, manifest = compile_contract(source, bindings)
    entry = manifest["contracts"][0]
    template = f"https://example.org/sm/{domain}"
    assert set(bindings["templates"]) == {template}
    assert entry["kind"] == "standalone_match"
    assert entry["dependencies"] == entry["requires_complete"] == [template]
    assert entry["shape"].endswith(("Dexpi" if exception else "Ecad") + f"AssetIntegrity_SC_{number}")
    left = URIRef(f"https://example.org/{domain}/hasLocalId")
    right = URIRef(f"https://example.org/{domain}/hasAssetIdentifier")
    data = Graph()
    expected = set()
    for i, (local, asset, valid) in enumerate([
        ("FI_101", "FI101", True), ("CV-1006", "CV1006", True),
        ("VC_105", "CV1006", False), ("TI_105", "TI1202", False),
        ("SC_101", "M1", exception), ("fi_101", "FI101", False),
        (None, "M1", False),
    ]):
        node = URIRef(f"urn:test:node:{i}")
        if local is not None:
            data.add((node, left, Literal(local)))
        data.add((node, right, URIRef("https://aas.example.com/" + asset)))
        if not valid:
            expected.add(str(node))
    other = URIRef("urn:test:unrelated")
    data.add((other, URIRef("https://example.org/opcuaconnectivity/hasAssetIdentifier"), URIRef("https://aas.example.com/M1")))
    rows = evaluate(source, bindings, data)[f"SC_{number}"]
    assert len(rows) == 7
    assert {n for n, row in rows.items() if not row["conforms"]} == expected
    conforms, report, _ = validate(data, shacl_graph=Graph().parse(data=ttl, format="turtle"))
    assert not conforms
    assert {str(n) for n in report.objects(None, SH.focusNode)} == expected
