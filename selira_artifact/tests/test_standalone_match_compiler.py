import base64
import pytest
from rdflib import Graph, Namespace, RDF, Literal, URIRef
from pyshacl import validate
from selira.compiler.shacl import compile_contract

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
