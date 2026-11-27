import json
from copy import deepcopy

import pytest
from rdflib import Literal

pytest.importorskip("aas_core3_1")
pytest.importorskip("semantic.template_lifting")
pytest.importorskip("pydantic", minversion="2.0")

from semantic.config import TARGETS
from semantic.ontoutils import compute_uri, semanticDict
from selira.runtime.aas_messages import AASChangeRequest
from selira.runtime.aas_candidate import stage_change
from selira.runtime.semantic_lifting import SemanticLiftingAdapter


@pytest.fixture
def context():
    domain, template, instance = next(t for t in TARGETS if t[0] == "assetinventory")
    document = json.loads(instance.read_text(encoding="utf-8"))
    adapter = SemanticLiftingAdapter(domain, json.loads(template.read_text(encoding="utf-8")))
    return document, adapter


def message(document, operation="UPDATE", path="Assets.TEP_Reactor.AssetName"):
    data = {
        "header": {"message_id": "MSG-001", "source": "Test"},
        "domain": {"name": "assetinventory", "submodel_id": document["id"]},
        "operation": {"type": operation, "id_short_path": path, "expected_version": 0},
    }
    if operation != "DELETE":
        data["payload"] = {"modelType": "Property", "idShort": path.split(".")[-1],
                           "valueType": "xs:string", "value": "Proposed"}
    return data


@pytest.mark.parametrize("operation,path", [
    ("UPDATE", "Assets.TEP_Reactor.AssetName"),
    ("CREATE", "Assets.TEP_Reactor.TestProperty"),
    ("DELETE", "Assets.TEP_Reactor.AssetName"),
])
def test_ic12_candidate_delta(context, operation, path):
    document, adapter = context
    original = deepcopy(document)
    change = AASChangeRequest.model_validate(message(document, operation, path))
    state = stage_change(document, change, adapter)
    assert document == original
    assert state.document != original
    assert set(state.previous_graph) == set(adapter.lift_instance(original))
    assert set(state.candidate_graph) == set(adapter.lift_instance(state.document))
    assert (set(state.previous_graph) - set(state.deletions)) | set(state.additions) == set(state.candidate_graph)
    assert not (set(state.additions) & set(state.deletions))
    parent = compute_uri(document["id"], "Assets.TEP_Reactor")
    predicate = semanticDict["ASSETINVENTORY"]["has" + path.split(".")[-1]]
    if operation != "CREATE":
        assert any(state.deletions.triples((parent, predicate, None)))
    if operation != "DELETE":
        assert any(str(value) == "Proposed" for value in state.additions.objects(parent, predicate))
    else:
        assert not list(state.candidate_graph.objects(parent, predicate))


@pytest.mark.parametrize("case", ["domain", "submodel", "semantic", "parent",
                                 "missing", "duplicate", "payload", "indexed"])
def test_ic12_candidate_invalid_target(context, case):
    document, adapter = context
    original = deepcopy(document)
    data = message(document)
    if case == "domain":
        data["domain"]["name"] = "dexpi"
    elif case == "submodel":
        data["domain"]["submodel_id"] = "urn:wrong"
    elif case == "semantic":
        data["domain"]["semantic_id"] = "urn:wrong"
    elif case == "parent":
        data["operation"]["id_short_path"] = "Missing.AssetName"
    elif case == "missing":
        data["operation"]["id_short_path"] = "Assets.TEP_Reactor.Missing"
        data["payload"]["idShort"] = "Missing"
    elif case == "duplicate":
        data["operation"]["type"] = "CREATE"
    elif case == "payload":
        data["payload"]["idShort"] = "Wrong"
    elif case == "indexed":
        data["operation"]["id_short_path"] = "Assets[0].AssetName"
    with pytest.raises(ValueError):
        stage_change(document, AASChangeRequest.model_validate(data), adapter)
    assert document == original


def test_ic12_candidate_noop(context):
    document, adapter = context
    data = message(document)
    reactor = next(e for e in document["submodelElements"][0]["value"]
                   if e["idShort"] == "TEP_Reactor")
    data["payload"] = deepcopy(next(e for e in reactor["value"] if e["idShort"] == "AssetName"))
    state = stage_change(document, AASChangeRequest.model_validate(data), adapter)
    assert not len(state.additions)
    assert not len(state.deletions)
    assert state.document == document
