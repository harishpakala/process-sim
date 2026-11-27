import pytest
import requests
from rdflib import Graph
from fastapi.testclient import TestClient
from test_ic12_aas_governance import service, request
from selira.runtime.governance_api import create_app
from selira.runtime.governance_client import GovernanceClient, GovernanceTransportUncertain


def test_ic12_client_end_to_end(service):
    coordinator, enabled = service
    with TestClient(create_app(aas_governance=coordinator)) as transport:
        client = GovernanceClient("http://testserver", session=transport)
        version = client.health()["version"]
        accepted = client.submit(request(coordinator))
        assert accepted.committed and accepted.repository_version == version + 1
        assert accepted.triggered_policies == ["LP-01"]
        assert [x.verdict for x in accepted.evaluated_contracts] == ["V"]
        rejected = client.submit(request(coordinator, field="ProductIdentifier",
                                        value="urn:nonexistent:product", asset="TEP_XMEAS1"))
        assert rejected.decision == "REJECTED" and not rejected.committed
        enabled[0] = False
        deferred = client.submit(request(coordinator))
        assert deferred.decision == "DEFERRED" and not deferred.committed
        assert client.health()["version"] == version + 1


def test_ic12_client_timeout_no_retry(service):
    coordinator, _ = service
    calls = []
    class Transport:
        def post(self, url, **kwargs):
            calls.append(url)
            raise requests.Timeout("lost response")
    with pytest.raises(GovernanceTransportUncertain):
        GovernanceClient(session=Transport()).submit(request(coordinator))
    assert len(calls) == 1


@pytest.mark.parametrize("domain,reserved,blocked", [
    ("asset-inventory", True, True), ("product-catalog", True, True),
    ("asset-inventory", False, False), ("product-catalog", False, False),
    ("dexpi", True, False)])
def test_ic12_publication_guard(monkeypatch, domain, reserved, blocked):
    from semantic import ontoutils as o
    calls = []
    class Response:
        status_code = 204
        def raise_for_status(self):
            pass
        def json(self):
            return {"boolean": reserved}
    def post(url, **kwargs):
        calls.append(url)
        return Response()
    monkeypatch.setattr(o.requests, "post", post)
    uri = o.compute_uri("https://example.org/sm/tep-" + domain +
                        ("" if domain == "asset-inventory" else "-instance"))
    if blocked:
        with pytest.raises(RuntimeError, match="governed publication blocked"):
            o.push_graph_to_graphdb(Graph(), uri)
        assert calls == [o.get_graphdb_repository_url()]
    else:
        o.push_graph_to_graphdb(Graph(), uri)
        assert calls[-1] == o.GRAPHDB_ENDPOINT
        assert len(calls) == (1 if domain == "dexpi" else 2)
