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


def test_ic12_governance_uncertain_commit(service, monkeypatch):
    from selira.runtime.graphdb_repository import RepositoryUncertain
    coordinator, _ = service
    change = request(coordinator)
    store = coordinator._manager.store
    before, version = store.snapshot()
    calls = []
    def fail(*args):
        calls.append(args)
        raise RepositoryUncertain("Commit not confirmed")
    monkeypatch.setattr(store, "compare_and_commit", fail)
    result = coordinator.submit(change)
    assert result.decision == "DEFERRED" and not result.committed
    assert [r.verdict for r in result.evaluated_contracts] == ["V"]
    assert result.repository_version == version
    assert coordinator._manager.history[-1]["verdict"] == "U"
    assert coordinator.submit(change).decision == "DEFERRED"
    assert len(calls) == 1
    assert set(store.snapshot()[0]) == set(before)
    with pytest.raises(RuntimeError, match="reconciliation"):
        coordinator.snapshot()


def test_ic12_governance_read_failure(service, monkeypatch):
    coordinator, _ = service
    change = request(coordinator)
    store = coordinator._manager.store
    def fail():
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(store, "snapshot", fail)
    result = coordinator.submit(change)
    assert result.decision == "DEFERRED" and not result.committed
    assert not result.evaluated_contracts
    assert result.repository_version == change.operation.expected_version


def test_ic12_manager_read_failure(service, monkeypatch):
    coordinator, _ = service
    manager = coordinator._manager
    graph, version = manager.store.snapshot()
    def fail():
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(manager.store, "snapshot", fail)
    result = manager.submit(graph, expected_version=version)
    assert result["verdict"] == "U" and not result["committed"]
    assert result["contracts"] == {}
    assert result["version"] == version


def test_ic12_governance_external_version_change(service):
    coordinator, _ = service
    change = request(coordinator)
    store = coordinator._manager.store
    graph, version = store.snapshot()
    assert store.compare_and_commit(version, graph) == (True, version + 1)
    assert coordinator.submit(change).decision == "DEFERRED"
    with pytest.raises(RuntimeError, match="reconciliation"):
        coordinator.snapshot()


@pytest.mark.parametrize("case,decision", [
    ("valid", "ACCEPTED"), ("invalid", "REJECTED"),
    ("evidence", "DEFERRED"), ("stale", "DEFERRED"),
    ("uncertain", "DEFERRED")])
def test_ic12_native_governance_commit_gate(service, monkeypatch, case, decision):
    from semantic.ontoutils import compute_uri
    from selira.runtime.graphdb_repository import RepositoryUncertain
    coordinator, enabled = service
    store = coordinator._manager.store
    original_commit = store.compare_and_commit
    before, _, version = coordinator.snapshot()
    calls = []

    def native_commit(expected, graph, documents, parts):
        calls.append((expected, graph, documents, parts))
        assert expected == version
        assert set(parts) == {str(compute_uri(key)) for key in documents}
        assert set().union(*(set(g) for g in parts.values())) == set(graph)
        for key, document in documents.items():
            assert set(parts[str(compute_uri(key))]) == set(
                coordinator._adapters[key].lift_instance(document))
        if case == "uncertain":
            raise RepositoryUncertain("Unconfirmed")
        return original_commit(expected, graph)

    def forbidden(*args):
        pytest.fail("RDF-only commit bypassed native path")

    monkeypatch.setattr(store, "compare_and_commit_native", native_commit, raising=False)
    monkeypatch.setattr(store, "compare_and_commit", forbidden)
    if case == "invalid":
        change = request(coordinator, field="ProductIdentifier",
                         value="urn:nonexistent:product", asset="TEP_XMEAS1")
    elif case == "stale":
        change = request(coordinator, version=0)
    else:
        change = request(coordinator)
    if case == "evidence":
        enabled[0] = False
    result = coordinator.submit(change)
    assert result.decision == decision
    assert len(calls) == int(case in ("valid", "uncertain"))
    if case == "valid":
        docs, graph, new_version = coordinator.snapshot()
        assert docs == calls[0][2] and docs != before
        assert set(graph) == set(calls[0][1])
        assert new_version == version + 1
    elif case == "uncertain":
        assert [r.verdict for r in result.evaluated_contracts] == ["V"]
        assert coordinator.submit(change).decision == "DEFERRED"
        assert len(calls) == 1
    else:
        assert coordinator.snapshot()[0] == before
        assert coordinator.snapshot()[2] == version


@pytest.mark.parametrize("case", ["valid", "mismatch", "evidence", "registration"])
def test_ic12_restart_recovery(service, monkeypatch, case):
    from copy import deepcopy
    from semantic.ontoutils import compute_uri
    coordinator, enabled = service
    registrations = [(doc, coordinator._adapters[key])
                     for key, doc in coordinator.snapshot()[0].items()]
    assert coordinator.submit(request(coordinator)).committed
    documents, graph, version = coordinator.snapshot()
    parts = {str(compute_uri(key)): coordinator._adapters[key].lift_instance(doc)
             for key, doc in documents.items()}
    persisted = deepcopy(documents)
    if case == "mismatch":
        next(iter(parts.values())).remove((None, None, None))
    elif case == "registration":
        persisted.pop(next(iter(persisted)))
    elif case == "evidence":
        enabled[0] = False
    store = coordinator._manager.store
    monkeypatch.setattr(store, "native_snapshot",
                        lambda: (persisted, parts, version, "a" * 32), raising=False)
    def forbidden(*args):
        pytest.fail("Recovery must not write")
    monkeypatch.setattr(store, "compare_and_commit", forbidden)
    monkeypatch.setattr(store, "compare_and_commit_native", forbidden, raising=False)
    def restart():
        return AASGovernance(coordinator._manager, registrations, coordinator._policies,
                             evidence_provider=coordinator._provider, recover=True)
    if case == "valid":
        recovered = restart()
        actual, rdf, v = recovered.snapshot()
        assert actual == documents and set(rdf) == set(graph) and v == version
        assert actual != dict((doc["id"], doc) for doc, _ in registrations)
    else:
        with pytest.raises(ValueError):
            restart()


@pytest.mark.parametrize("case", ["confirmed", "pending"])
def test_ic12_request_replay(service, monkeypatch, case):
    from selira.runtime.graphdb_repository import RepositoryUncertain
    coordinator, _ = service
    store = coordinator._manager.store
    original = store.compare_and_commit
    records = {}
    context = []
    calls = []
    def lookup(source, message_id, fingerprint):
        row = records.get((source, message_id))
        if row is None:
            return None
        if row[0] != fingerprint:
            raise ValueError("Conflicting message ID reuse")
        return row[1]
    def set_context(*args):
        context[:] = args
    def native_commit(expected, graph, documents, parts):
        calls.append(expected)
        source, message_id, fingerprint, response = context
        records[(source, message_id)] = (
            fingerprint, response if case == "confirmed" else {"pending": True})
        if case == "pending":
            raise RepositoryUncertain("Interrupted")
        return original(expected, graph)
    monkeypatch.setattr(store, "request_outcome", lookup, raising=False)
    monkeypatch.setattr(store, "set_request_context", set_context, raising=False)
    monkeypatch.setattr(store, "clear_request_context", context.clear, raising=False)
    monkeypatch.setattr(store, "compare_and_commit_native", native_commit, raising=False)
    change = request(coordinator)
    conflicting = request(coordinator, value="Different value")
    first = coordinator.submit(change)
    second = coordinator.submit(change)
    assert first.decision == second.decision == (
        "ACCEPTED" if case == "confirmed" else "DEFERRED")
    if case == "confirmed":
        assert first == second
    assert len(calls) == 1
    assert not context
    with pytest.raises(ValueError, match="Conflicting"):
        coordinator.submit(conflicting)
    assert len(calls) == 1

def test_ic12_qualification_context_reports_server_attestations(service):
    coordinator, enabled = service
    context = coordinator.qualification_context()
    assert context["version"] == coordinator.snapshot()[2]
    assert set(context["evidence_complete"]) == {
        adapter.template_id for adapter in coordinator._adapters.values()
    }
    assert context["identity_normalized"] is True
    assert context["applicability_confirmed"] is True
    assert context["source"] == "server_operator_attestation"

    enabled[0] = False
    incomplete = coordinator.qualification_context()
    assert incomplete["version"] == context["version"]
    assert incomplete["evidence_complete"] == []
    assert incomplete["identity_normalized"] is False
    assert incomplete["applicability_confirmed"] is False

def test_ic12_qualification_context_update_is_version_guarded(service):
    coordinator, _ = service
    stored = {}
    coordinator._provider.update = lambda flags: stored.update(flags)
    context = coordinator.qualification_context()
    proposed = {
        "evidence_complete": context["available_scopes"][:1],
        "identity_normalized": False,
        "applicability_confirmed": True,
    }
    updated = coordinator.update_qualification_context(
        proposed, expected_version=context["version"])
    assert stored == proposed
    assert updated["evidence_complete"] == proposed["evidence_complete"]
    assert updated["identity_normalized"] is False
    assert updated["applicability_confirmed"] is True
    assert updated["version"] == context["version"]
    with pytest.raises(ValueError, match="Stale"):
        coordinator.update_qualification_context(proposed, expected_version=-1)
    with pytest.raises(ValueError, match="registered"):
        coordinator.update_qualification_context(
            {**proposed, "evidence_complete": ["urn:unregistered:template"]},
            expected_version=context["version"])

