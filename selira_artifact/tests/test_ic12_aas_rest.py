import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from selira.runtime.governance_api import create_app
from test_ic12_aas_governance import service, request


@pytest.mark.parametrize("operation", ["CREATE", "UPDATE", "DELETE"])
def test_ic12_rest_accept(service, operation):
    coordinator, _ = service
    client = TestClient(create_app(aas_governance=coordinator))
    data = request(coordinator).model_dump()
    data["operation"]["type"] = operation
    if operation == "CREATE":
        data["operation"]["id_short_path"] = "Assets.TEP_Reactor.TestProperty"
        data["payload"]["idShort"] = "TestProperty"
    elif operation == "DELETE":
        data["payload"] = None
    else:
        data["policy"] = {"policy_id": "LP-01", "activation_terminal": "START"}
    version = coordinator.snapshot()[2]
    result = client.post("/api/v1/changes/aas", json=data)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["decision"] == "ACCEPTED" and body["committed"]
    assert body["triggered_policies"] == ["LP-01"]
    assert body["evaluated_contracts"][0]["verdict"] == "V"
    assert body["repository_version"] == version + 1
    assert client.get("/api/v1/health").json()["version"] == version + 1


@pytest.mark.parametrize("case,status,decision", [
    ("invalid", 200, "REJECTED"), ("evidence", 200, "DEFERRED"),
    ("stale", 200, "DEFERRED"), ("malformed", 422, None),
    ("terminal", 422, None), ("rdf", 409, None)])
def test_ic12_rest_preserves_state(service, case, status, decision):
    coordinator, enabled = service
    client = TestClient(create_app(aas_governance=coordinator))
    before, graph, version = coordinator.snapshot()
    data = request(coordinator).model_dump()
    endpoint = "/api/v1/changes/aas"
    if case == "invalid":
        data = request(coordinator, field="ProductIdentifier", asset="TEP_XMEAS1",
                       value="urn:nonexistent:product").model_dump()
    elif case == "evidence":
        enabled[0] = False
    elif case == "stale":
        data["operation"]["expected_version"] = 0
    elif case == "malformed":
        data["payload"] = None
    elif case == "terminal":
        data["policy"] = {"policy_id": "LP-01", "activation_terminal": "DONE"}
    else:
        endpoint = "/api/v1/changes"
        data = {"expected_version": version, "additions": [
            {"subject": "urn:s", "predicate": "urn:p",
             "object": {"kind": "literal", "value": "bypass"}}]}
    result = client.post(endpoint, json=data)
    assert result.status_code == status, result.text
    if decision:
        assert result.json()["decision"] == decision
        assert not result.json()["committed"]
    after, actual, new_version = coordinator.snapshot()
    assert after == before and set(actual) == set(graph) and new_version == version


def test_ic12_rest_exclusive_modes():
    with pytest.raises(ValueError):
        create_app()
    with pytest.raises(ValueError):
        create_app(object(), aas_governance=object())
