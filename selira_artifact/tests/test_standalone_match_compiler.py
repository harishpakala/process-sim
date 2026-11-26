import base64
import pytest
from rdflib import Graph, Namespace, RDF, Literal, URIRef
from pyshacl import validate
from selira.compiler.shacl import compile_contract
from selira.formal.reference_evaluator import evaluate

EX = Namespace("https://example.org/test/")
BASE = "https://aas.example.com/"
SOURCE = ('Specification Test { Ref SubmodelTemplate sources = "' +
          base64.b64encode(b"urn:test").decode() +
          '"; Contract SC_02 { forall source in sources { matches(source.LocalId, source.AssetIdentifier); } } }')
BINDINGS = {"templates": {"urn:test": {
    "class": str(EX.Device),
    "fields": {"LocalId": str(EX.local), "AssetIdentifier": str(EX.asset)},
    "comparison_policy": {"kind": "normalized_asset_identifier",
                          "exceptions": [["SC_101", BASE + "M1"]]}
}}}


@pytest.mark.parametrize("local,asset,expected", [
    ("FI_101", "FI101", True), ("VC_105", "CV1006", False),
    ("SC_101", "M1", True), ("SC_101", "M2", False),
    ("fi_101", "FI101", False), (None, "M1", False),
    ("M1", None, False), ("---", "M1", False),
])
def test_compiled_match(local, asset, expected):
    ttl, manifest = compile_contract(SOURCE, BINDINGS)
    assert manifest["contracts"][0]["kind"] == "standalone_match"
    data = Graph()
    data.add((EX.device, RDF.type, EX.Device))
    if local is not None:
        data.add((EX.device, EX.local, Literal(local)))
    if asset is not None:
        data.add((EX.device, EX.asset, URIRef(BASE + asset)))
    conforms, _, _ = validate(data, shacl_graph=Graph().parse(data=ttl, format="turtle"))
    assert conforms == expected

    rows = evaluate(SOURCE, BINDINGS, data)["SC_02"]
    assert rows[str(EX.device)]["conforms"] == expected


@pytest.mark.parametrize("predicate_scope", [False, True])
def test_multiple_values_and_scope(predicate_scope):
    import copy
    bindings = copy.deepcopy(BINDINGS)
    bindings["templates"]["urn:test"]["target_by_predicate"] = predicate_scope
    data = Graph()
    data.add((EX.device, RDF.type, EX.Device))
    data.add((EX.device, EX.local, Literal("M1")))
    data.add((EX.device, EX.local, Literal("M2")))
    data.add((EX.device, EX.asset, URIRef(BASE + "M1")))
    data.add((EX.other, EX.asset, URIRef(BASE + "M1")))
    data.add((EX.other, EX.local, Literal("M1")))
    rows = evaluate(SOURCE, bindings, data)["SC_02"]
    assert not rows[str(EX.device)]["conforms"]
    assert (str(EX.other) in rows) == predicate_scope
    ttl, _ = compile_contract(SOURCE, bindings)
    conforms, report, _ = validate(data, shacl_graph=Graph().parse(data=ttl, format="turtle"))
    from rdflib.namespace import SH
    assert not conforms
    assert {str(n) for n in report.objects(None, SH.focusNode)} == {
        node for node, row in rows.items() if not row["conforms"]
    }
