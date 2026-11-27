"""Opt-in adoption test. Only use an empty dedicated SELIRA_TEST repository."""
import json
import os
from urllib.parse import urlsplit

import pytest

ENDPOINT = os.getenv("SELIRA_TEST_GRAPHDB_ENDPOINT")
pytestmark = pytest.mark.skipif(not ENDPOINT, reason="Live GraphDB endpoint not configured")


def test_ic12_live_adoption(tmp_path):
    import requests
    from rdflib import Graph
    from semantic.config import TARGETS
    from semantic.ontoutils import compute_uri
    from selira.runtime.semantic_lifting import SemanticLiftingAdapter
    from selira.runtime.graphdb_repository import GraphDBRepository, rdf11_triples
    from selira.runtime.governance_server import build_service
    from fastapi.testclient import TestClient

    endpoint = ENDPOINT.rstrip("/")
    parsed = urlsplit(endpoint)
    assert parsed.scheme in ("http", "https") and parsed.path == "/repositories/SELIRA_TEST"
    assert not parsed.query and not parsed.fragment
    def query(q):
        r = requests.post(endpoint, data={"query": q, "infer": "false"},
                          headers={"Accept": "application/sparql-results+json"}, timeout=60)
        r.raise_for_status()
        return r.json()
    def update(q):
        r = requests.post(endpoint + "/statements", data=q.encode("utf-8"),
                          headers={"Content-Type": "application/sparql-update"}, timeout=60)
        r.raise_for_status()
    assert not query("ASK { { GRAPH ?g { ?s ?p ?o } } UNION { ?s ?p ?o } }")["boolean"]
    registrations = [(json.loads(i.read_text(encoding="utf-8")),
                      SemanticLiftingAdapter(d, json.loads(t.read_text(encoding="utf-8"))))
                     for d,t,i in TARGETS if d in ("assetinventory", "productcatalog")]
    parts = {str(compute_uri(d["id"])): a.lift_instance(d) for d,a in registrations}
    docs = {d["id"]: d for d,a in registrations}
    for key, graph in parts.items():
        update("INSERT DATA { GRAPH <" + key + "> { " +
               " ".join(f"{s.n3()} {p.n3()} {o.n3()} ." for s,p,o in graph) + " } }")
    update('INSERT DATA { GRAPH <urn:selira:test:unrelated> { <urn:s> <urn:p> "sentinel" } }')
    journal = tmp_path / "adoption.sqlite"
    evidence = tmp_path / "evidence.json"
    def flags(complete):
        evidence.write_text(json.dumps(dict(evidence_complete=[a.template_id for _,a in registrations] if complete else [],
                            identity_normalized=complete, applicability_confirmed=complete)), encoding="utf-8")
    store = GraphDBRepository(endpoint, list(parts), native_mode=True)
    assert store.inspect_adoption(parts)["eligible"]
    key = next(iter(parts))
    update(f'INSERT DATA {{ GRAPH <{key}> {{ <urn:unexpected> <urn:p> "extra" }} }}')
    assert not store.inspect_adoption(parts)["eligible"]
    update(f'DELETE DATA {{ GRAPH <{key}> {{ <urn:unexpected> <urn:p> "extra" }} }}')
    flags(False)
    with pytest.raises(ValueError, match="Adoption not qualified"):
        build_service(endpoint, journal, mode="adopt", evidence_file=evidence)
    assert store.inspect_adoption(parts)["eligible"]
    flags(True)
    # Simulate loss of the adoption response after the server completed it.
    from selira.runtime.graphdb_repository import RepositoryUncertain
    class LostResponse:
        def post(self, url, **kwargs):
            response = requests.post(url, **kwargs)
            if url.endswith("/statements"):
                response.raise_for_status()
                raise RuntimeError("Simulated lost adoption response")
            return response
    interrupted = GraphDBRepository(endpoint, list(parts), native_mode=True,
                                    journal_path=journal, session=LostResponse())
    with pytest.raises(RepositoryUncertain, match="Adoption outcome unresolved"):
        interrupted.adopt_qualified(docs, parts)
    assert interrupted.pending_commit()[1] == -1
    interrupted._journal.close()
    with pytest.raises(RuntimeError, match="reconciliation"):
        build_service(endpoint, journal, mode="recover", evidence_file=evidence)
    with pytest.raises(RepositoryUncertain):
        build_service(endpoint, journal, mode="reconcile", evidence_file=evidence)
    assert build_service(endpoint, journal, mode="reconcile", evidence_file=evidence,
                         remote_quiescent=True) == {"status": "COMMITTED"}
    app = build_service(endpoint, journal, mode="recover", evidence_file=evidence)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok", "version": 1}
    saved, actual, version, token = store.native_snapshot()
    assert saved == docs and version == 1 and token
    assert all(rdf11_triples(actual[k]) == rdf11_triples(parts[k]) for k in parts)
    assert query('ASK { GRAPH <urn:selira:test:unrelated> { <urn:s> <urn:p> "sentinel" } }')["boolean"]
    assert not store.inspect_adoption(parts)["eligible"]
    recovered = build_service(endpoint, journal, mode="recover", evidence_file=evidence)
    with TestClient(recovered) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok", "version": 1}
    assert store.native_snapshot()[2:] == (version, token)
