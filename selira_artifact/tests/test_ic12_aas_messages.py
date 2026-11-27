import pytest

pytest.importorskip("pydantic", minversion="2.0")
from pydantic import ValidationError
from selira.runtime.aas_messages import AASChangeRequest, AASChangeResponse


def message():
    return {
        "header": {"message_id": "MSG-001", "source": "EngineeringApplication"},
        "domain": {"name": "AssetInventory", "submodel_id": "urn:example:inventory"},
        "operation": {"type": "UPDATE", "id_short_path": "Asset101.ProductReference",
                      "expected_version": 12},
        "payload": {"modelType": "Property", "idShort": "ProductReference",
                    "valueType": "xs:string", "value": " P-200 ",
                    "semanticId": {"type": "ExternalReference", "keys": [
                        {"type": "GlobalReference", "value": "urn:example:product-ref"}]}}
    }


@pytest.mark.parametrize("explicit", [False, True])
def test_ic12_message_invocation_intent(explicit):
    data = message()
    if explicit:
        data["policy"] = {"policy_id": "LP-01", "activation_terminal": "START"}
    parsed = AASChangeRequest.model_validate(data)
    assert (parsed.policy is not None) == explicit
    assert parsed.payload == data["payload"]


@pytest.mark.parametrize("operation", ["CREATE", "UPDATE"])
def test_ic12_message_requires_payload(operation):
    data = message()
    data["operation"]["type"] = operation
    del data["payload"]
    with pytest.raises(ValidationError):
        AASChangeRequest.model_validate(data)


def test_ic12_message_delete():
    data = message()
    data["operation"]["type"] = "DELETE"
    with pytest.raises(ValidationError):
        AASChangeRequest.model_validate(data)
    del data["payload"]
    assert AASChangeRequest.model_validate(data).payload is None


@pytest.mark.parametrize("version", [-1, True, "12"])
def test_ic12_message_invalid_version(version):
    data = message()
    data["operation"]["expected_version"] = version
    with pytest.raises(ValidationError):
        AASChangeRequest.model_validate(data)


def test_ic12_message_no_client_evidence():
    data = message()
    data["coverage_attested"] = True
    with pytest.raises(ValidationError):
        AASChangeRequest.model_validate(data)


def test_ic12_message_model_type_required():
    data = message()
    del data["payload"]["modelType"]
    with pytest.raises(ValidationError):
        AASChangeRequest.model_validate(data)


@pytest.mark.parametrize("decision,committed", [
    ("ACCEPTED", True), ("REJECTED", False), ("DEFERRED", False)])
def test_ic12_response_valid(decision, committed):
    data = {"message_id": "MSG-001", "decision": decision,
            "committed": committed, "repository_version": 12}
    assert AASChangeResponse.model_validate(data).committed == committed
    data["committed"] = not committed
    with pytest.raises(ValidationError):
        AASChangeResponse.model_validate(data)
