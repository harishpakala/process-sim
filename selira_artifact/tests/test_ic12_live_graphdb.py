"""Opt-in integration against a dedicated, initially empty SELIRA_TEST repository.

No repository creation, clearing or deletion is performed. Use a fresh test
repository for each run. Never point this suite at operational data.
"""
import json
import os
from urllib.parse import urlsplit

import pytest

ENDPOINT = os.getenv("SELIRA_TEST_GRAPHDB_ENDPOINT")
pytestmark = pytest.mark.skipif(not ENDPOINT, reason="Live GraphDB endpoint not configured")


def test_ic12_live_graphdb_lifecycle(tmp_path):
    import requests
    from rdflib import Graph, URIRef, Literal
    from semantic.config import TARGETS
    from semantic.ontoutils import compute_uri
    from selira.runtime.graphdb_repository import GraphDBRepository, rdf11_triples
    from selira.runtime.aas_governance import AASGovernance
    from selira.runtime.automation_manager import MultiContractAutomationManager
    from selira.runtime.semantic_lifting import SemanticLiftingAdapter
    from selira.language.parser.frontend import parse_safsl
    from test_ic12_aas_governance import ROOT, request

    endpoint = ENDPOINT.rstrip("/")
    parsed = urlsplit(endpoint)
    assert parsed.scheme in ("http", "https") and parsed.path == "/repositories/SELIRA_TEST"
    assert not parsed.query and not parsed.fragment
    session = requests.Session()
    def update(query):
        response = session.post(endpoint + "/statements", data=query.encode("utf-8"),
            headers={"Content-Type": "application/sparql-update"}, timeout=60)
        response.raise_for_status()
    def ask(query):
        response = session.post(endpoint, data={"query": query, "infer": "false"},
            headers={"Accept": "application/sparql-results+json"}, timeout=60)
        response.raise_for_status()
        return response.json()["boolean"]
    assert not ask("ASK { { GRAPH ?g { ?s ?p ?o } } UNION { ?s ?p ?o } }"), "Use an empty test repository"
    registrations = [(json.loads(instance.read_text(encoding="utf-8")),
                      SemanticLiftingAdapter(domain, json.loads(template.read_text(encoding="utf-8"))))
                     for domain, template, instance in TARGETS
                     if domain in ("assetinventory", "productcatalog")]
    graphs = [str(compute_uri(doc["id"])) for doc, _ in registrations]
    journal = tmp_path / "commit.sqlite"
    flags = dict(evidence_complete=[a.template_id for _, a in registrations],
                 identity_normalized=True, applicability_confirmed=True)
    enabled = [True]
    policies = {"LP-01": parse_safsl((ROOT / "policies/LP-01.safsl").read_text(encoding="utf-8")).children[0]}
    def open_store(transport=session):
        return GraphDBRepository(endpoint, graphs, session=transport,
                                 native_mode=True, journal_path=journal)
    def coordinator(store, recover=False):
        manager = MultiContractAutomationManager([(ROOT / "contracts/SC-01.safsl",
                                                   ROOT / "bindings/SC-01.json")], store=store)
        return AASGovernance(manager, registrations, policies, recover=recover,
                             evidence_provider=lambda old, new: flags if enabled[0] else {})
    def change(service, mid, **kwargs):
        req = request(service, **kwargs)
        return req.model_copy(update={"header": req.header.model_copy(update={"message_id": mid})})
    def coherent(store, service):
        docs, parts, version, token = store.native_snapshot()
        actual, graph, observed = service.snapshot()
        assert docs == actual and version == observed and token
        assert set().union(*(set(g) for g in parts.values())) == set(graph)
        for doc, adapter in registrations:
            key = doc["id"]
            persisted = rdf11_triples(parts[str(compute_uri(key))])
            lifted = rdf11_triples(adapter.lift_instance(docs[key]))
            extra, missing = persisted - lifted, lifted - persisted
            if extra or missing:
                def describe(triples):
                    return "\n".join(" ".join(term.n3() for term in triple)
                                     for triple in sorted(triples, key=lambda t: tuple(x.n3() for x in t))[:5])
                pytest.fail(f"RDF round-trip mismatch for {key}: "
                            f"persisted={len(persisted)}, lifted={len(lifted)}, "
                            f"extra={len(extra)}, missing={len(missing)}\n"
                            f"Persisted only:\n{describe(extra)}\n"
                            f"Lifted only:\n{describe(missing)}", pytrace=False)
        return docs, version

    update('INSERT DATA { GRAPH <urn:selira:test:unrelated> { <urn:s> <urn:p> "sentinel" } }')
    store = open_store()
    assert store.initialize_empty() == 0
    service = coordinator(store)
    initial, version = coherent(store, service)
    assert version == 1
    valid = change(service, "valid", value="Reactor Ω")
    accepted = service.submit(valid)
    assert accepted.committed and accepted.decision == "ACCEPTED"
    assert [r.verdict for r in accepted.evaluated_contracts] == ["V"]
    admitted, version = coherent(store, service)
    assert admitted != initial and version == 2
    assert service.submit(valid) == accepted
    invalid = change(service, "invalid", field="ProductIdentifier",
                     value="urn:nonexistent:product", asset="TEP_XMEAS1")
    rejected = service.submit(invalid)
    assert rejected.decision == "REJECTED" and not rejected.committed
    assert [r.verdict for r in rejected.evaluated_contracts] == ["F"]
    enabled[0] = False
    deferred = service.submit(change(service, "missing-evidence"))
    assert deferred.decision == "DEFERRED" and not deferred.committed
    assert [r.verdict for r in deferred.evaluated_contracts] == ["U"]
    enabled[0] = True
    assert service.submit(change(service, "stale", version=1)).decision == "DEFERRED"
    assert coherent(store, service) == (admitted, version)
    store._journal.close()
    store = open_store()
    service = coordinator(store, recover=True)
    assert coherent(store, service) == (admitted, version)
    assert service.submit(valid) == accepted
    store._journal.close()

    # Inject a lost response only AFTER the actual server update has returned.
    # This establishes remote quiescence for this controlled failure scenario.
    class LostResponse:
        def post(self, url, **kwargs):
            response = session.post(url, **kwargs)
            if url.endswith("/statements"):
                response.raise_for_status()
                raise RuntimeError("Simulated lost response after completed update")
            return response
    store = open_store(LostResponse())
    service = coordinator(store, recover=True)
    interrupted = change(service, "interrupted", value="Recovered reactor")
    result = service.submit(interrupted)
    assert result.decision == "DEFERRED" and not result.committed
    assert store.pending_commit() is not None
    assert service.submit(interrupted).decision == "DEFERRED"
    store._journal.close()
    store = open_store()
    with pytest.raises(RuntimeError, match="reconciliation"):
        coordinator(store, recover=True)
    assert store.reconcile_pending(remote_quiescent=True) == "COMMITTED"
    service = coordinator(store, recover=True)
    replay = service.submit(interrupted)
    assert replay.committed and replay.repository_version == version + 1
    final, observed = coherent(store, service)
    assert final != admitted and observed == version + 1
    assert ask('ASK { GRAPH <urn:selira:test:unrelated> { <urn:s> <urn:p> "sentinel" } }')
    store._journal.close()
    session.close()
