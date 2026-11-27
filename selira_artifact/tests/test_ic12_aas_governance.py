import json
from pathlib import Path

import pytest

pytest.importorskip("aas_core3_1")
pytest.importorskip("semantic.template_lifting")
pytest.importorskip("pydantic", minversion="2.0")

from semantic.config import TARGETS
from selira.language.parser.frontend import parse_safsl
from selira.runtime.aas_messages import AASChangeRequest
from selira.runtime.aas_governance import AASGovernance
from selira.runtime.automation_manager import MultiContractAutomationManager
from selira.runtime.semantic_lifting import SemanticLiftingAdapter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service():
    registrations = []
    for domain, template, instance in TARGETS:
        if domain in ("assetinventory", "productcatalog"):
            registrations.append((json.loads(instance.read_text(encoding="utf-8")),
                                  SemanticLiftingAdapter(domain, json.loads(template.read_text(encoding="utf-8")))))
    manager = MultiContractAutomationManager([(ROOT / "contracts/SC-01.safsl",
                                               ROOT / "bindings/SC-01.json")])
    spec = parse_safsl((ROOT / "policies/LP-01.safsl").read_text(encoding="utf-8")).children[0]
    flags = dict(evidence_complete=[a.template_id for _, a in registrations],
                 identity_normalized=True, applicability_confirmed=True)
    enabled = [True]
    coordinator = AASGovernance(manager, registrations, {"LP-01": spec},
                                evidence_provider=lambda old, new: flags if enabled[0] else {})
    return coordinator, enabled


def request(coordinator, *, field="AssetName", value="Updated reactor", version=None, asset="TEP_Reactor"):
    documents, _, current_version = coordinator.snapshot()
    document = next(d for d in documents.values() if d["idShort"] == "AssetInventory")
    return AASChangeRequest.model_validate({
        "header": {"message_id": "MSG-1", "source": "test"},
        "domain": {"name": "assetinventory", "submodel_id": document["id"]},
        "operation": {"type": "UPDATE", "id_short_path": "Assets." + asset + "." + field,
                      "expected_version": current_version if version is None else version},
        "payload": {"modelType": "Property", "idShort": field,
                    "valueType": "xs:string", "value": value}})


def test_ic12_governance_accept(service):
    coordinator, _ = service
    old_docs, old_graph, version = coordinator.snapshot()
    result = coordinator.submit(request(coordinator))
    docs, graph, new_version = coordinator.snapshot()
    assert result.decision == "ACCEPTED" and result.committed
    assert result.triggered_policies == ["LP-01"]
    assert [r.verdict for r in result.evaluated_contracts] == ["V"]
    assert new_version == result.repository_version == version + 1
    assert docs != old_docs and set(graph) != set(old_graph)


@pytest.mark.parametrize("case,decision", [
    ("invalid", "REJECTED"), ("evidence", "DEFERRED"), ("stale", "DEFERRED")])
def test_ic12_governance_preserves_state(service, case, decision):
    coordinator, enabled = service
    before, graph, version = coordinator.snapshot()
    if case == "invalid":
        change = request(coordinator, field="ProductIdentifier", value="urn:nonexistent:product", asset="TEP_XMEAS1")
    elif case == "evidence":
        enabled[0] = False
        change = request(coordinator)
    else:
        change = request(coordinator, version=0)
    result = coordinator.submit(change)
    after, actual, new_version = coordinator.snapshot()
    assert result.decision == decision and not result.committed
    assert after == before and set(actual) == set(graph)
    assert new_version == result.repository_version == version


def test_ic12_governance_snapshot_isolation(service):
    coordinator, _ = service
    docs, graph, version = coordinator.snapshot()
    docs.clear()
    graph.remove((None, None, None))
    actual, actual_graph, actual_version = coordinator.snapshot()
    assert actual and len(actual_graph) and actual_version == version
