import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import XSD
from selira.runtime.graphdb_repository import GraphDBRepository


class Session:
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail

    def post(self, endpoint, **kwargs):
        self.endpoint = endpoint
        self.kwargs = kwargs
        return self

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("Repository unavailable")

    def json(self):
        return {"results": {"bindings": self.rows}}


def version(n="1"):
    return {"type": "literal", "datatype": str(XSD.integer), "value": n}


def uri(value):
    return {"type": "uri", "value": value}


def repo(session):
    return GraphDBRepository("http://graphdb:7200/repositories/AAST",
                             ["urn:asset", "urn:product"], session=session)


def test_ic12_graphdb_snapshot():
    row = {"version": version(), "g": uri("urn:asset"),
           "s": uri("urn:s"), "p": uri("urn:p"),
           "o": {"type": "literal", "datatype": str(XSD.integer), "value": "01"}}
    session = Session([row])
    graph, v = repo(session).snapshot()
    assert v == 1
    assert (URIRef("urn:s"), URIRef("urn:p"),
            Literal("01", datatype=XSD.integer, normalize=False)) in graph
    assert session.kwargs["data"]["infer"] == "false"
    assert "VALUES ?g { <urn:asset> <urn:product> }" in session.kwargs["data"]["query"]
    assert session.endpoint.endswith("/repositories/AAST")


def test_ic12_graphdb_empty():
    graph, v = repo(Session([{"version": version("0")}])).snapshot()
    assert len(graph) == 0 and v == 0


@pytest.mark.parametrize("rows", [
    [],
    [{"version": version("1")}, {"version": version("2")}],
    [{"version": version("-1")}],
    [{"version": {"type": "literal", "value": "1"}}],
    [{"version": version(), "g": uri("urn:other")}],
])
def test_ic12_graphdb_invalid_snapshot(rows):
    with pytest.raises(ValueError):
        repo(Session(rows)).snapshot()


def test_ic12_graphdb_transport_failure():
    with pytest.raises(RuntimeError):
        repo(Session([], fail=True)).snapshot()


@pytest.mark.parametrize("graphs", [[], ["urn:selira:repository:metadata"],
                                    ["urn:bad> }"]])
def test_ic12_graphdb_invalid_scope(graphs):
    with pytest.raises(ValueError):
        GraphDBRepository("http://graphdb/repositories/AAST", graphs, session=Session([]))


def test_ic12_graphdb_read_only():
    with pytest.raises(NotImplementedError):
        repo(Session([])).compare_and_commit(0, None)


from rdflib import Graph
from selira.runtime.graphdb_repository import RepositoryUncertain


class WriteSession(Session):
    def __init__(self, *, confirm=True, fail_write=False):
        super().__init__([{"version": version()}])
        self.confirm = confirm
        self.fail_write = fail_write
        self.updates = []

    def post(self, endpoint, **kwargs):
        import re
        if endpoint.endswith("/statements"):
            query = kwargs["data"].decode()
            self.updates.append(query)
            self.token = re.search(r'<urn:selira:commitToken> "([0-9a-f]+)"', query)[1]
            if self.fail_write:
                raise RuntimeError("Lost connection")
        elif "SELECT ?token" in kwargs["data"]["query"]:
            self.rows = [{"token": {"type": "literal",
                          "value": self.token if self.confirm else "other"}}]
        return super().post(endpoint, **kwargs)


def writable(session):
    return GraphDBRepository("http://graphdb/repositories/AAST",
                             ["urn:asset", "urn:product"], session=session,
                             partition=lambda g: {"urn:asset": g, "urn:product": Graph()})


def test_ic12_graphdb_confirmed_write():
    session = WriteSession()
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("urn:p"), Literal("new")))
    assert writable(session).compare_and_commit(1, graph) == (True, 2)
    query, = session.updates
    assert "DELETE" in query and "INSERT" in query
    assert 'GRAPH <urn:asset>' in query and 'GRAPH <urn:product>' in query
    assert '<urn:s> <urn:p> "new"' in query
    assert "FILTER NOT EXISTS" in query


def test_ic12_graphdb_stale_write():
    session = WriteSession()
    assert writable(session).compare_and_commit(0, Graph()) == (False, 1)
    assert not session.updates


@pytest.mark.parametrize("options", [{"confirm": False}, {"fail_write": True}])
def test_ic12_graphdb_uncertain_write(options):
    session = WriteSession(**options)
    repository = writable(session)
    with pytest.raises(RepositoryUncertain):
        repository.compare_and_commit(1, Graph())
    with pytest.raises(RepositoryUncertain):
        repository.compare_and_commit(1, Graph())
    assert len(session.updates) == 1


def test_ic12_graphdb_invalid_partition():
    session = WriteSession()
    repository = GraphDBRepository("http://graphdb/repositories/AAST",
        ["urn:asset"], session=session, partition=lambda g: {"urn:other": g})
    with pytest.raises(ValueError):
        repository.compare_and_commit(1, Graph())
    assert not session.updates


def native_repository(session):
    return GraphDBRepository("http://graphdb/repositories/AAST",
                             ["urn:asset", "urn:product"], session=session,
                             native_mode=True)


def test_ic12_native_combined_update():
    import json
    from rdflib.plugins.sparql.parser import parseUpdate
    session = WriteSession()
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("urn:p"), Literal("new")))
    docs = {"urn:asset": {"id": "urn:asset", "idShort": 'Asset "A"\nΩ'}}
    assert native_repository(session).compare_and_commit_native(
        1, graph, docs, {"urn:asset": graph, "urn:product": Graph()}) == (True, 2)
    query, = session.updates
    parseUpdate(query)
    assert "GRAPH <urn:selira:repository:native>" in query
    assert "<urn:selira:documents> ?oldDocuments" in query
    assert Literal(json.dumps(docs, ensure_ascii=False, sort_keys=True,
                              allow_nan=False)).n3() in query
    assert '<urn:s> <urn:p> "new"' in query
    assert "<urn:selira:version>" in query
    assert "<urn:selira:commitToken>" in query


def test_ic12_native_reject_rdf_only():
    session = WriteSession()
    with pytest.raises(ValueError, match="RDF-only"):
        native_repository(session).compare_and_commit(1, Graph())
    assert not session.updates


@pytest.mark.parametrize("case", ["identity", "partition", "union", "stale"])
def test_ic12_native_no_invalid_write(case):
    session = WriteSession()
    repository = native_repository(session)
    graph = Graph()
    docs = {"urn:asset": {"id": "urn:asset"}}
    parts = {"urn:asset": Graph(), "urn:product": Graph()}
    if case == "identity":
        docs["urn:asset"]["id"] = "urn:other"
    elif case == "partition":
        del parts["urn:product"]
    elif case == "union":
        graph.add((URIRef("urn:s"), URIRef("urn:p"), Literal("new")))
    if case == "stale":
        assert repository.compare_and_commit_native(0, graph, docs, parts) == (False, 1)
    else:
        with pytest.raises(ValueError):
            repository.compare_and_commit_native(1, graph, docs, parts)
    assert not session.updates


@pytest.mark.parametrize("case", ["empty", "existing", "unexpected"])
def test_ic12_bootstrap(case):
    from rdflib.plugins.sparql.parser import parseUpdate, parseQuery
    class BootstrapSession(Session):
        def post(self, endpoint, **kwargs):
            self.kwargs = kwargs
            if endpoint.endswith("/statements"):
                query = kwargs["data"].decode()
                parseUpdate(query)
                assert "DELETE" not in query and "FILTER NOT EXISTS" in query
            else:
                parseQuery(kwargs["data"]["query"])
            return self

        def json(self):
            if self.kwargs["data"]["query"].startswith("ASK"):
                return {"boolean": case == "unexpected"}
            return {"results": {"bindings": [
                {"version": version("1" if case == "existing" else "0")}]}}
    repository = native_repository(BootstrapSession([]))
    if case == "empty":
        assert repository.initialize_empty() == 0
    else:
        with pytest.raises(ValueError):
            repository.initialize_empty()


@pytest.mark.parametrize("case", ["valid", "missing", "duplicate", "identity", "partial"])
def test_ic12_native_snapshot(case):
    import json
    row = {"version": version("2"),
           "token": {"type": "literal", "value": "a" * 32},
           "documents": {"type": "literal", "value": json.dumps(
               {"urn:asset": {"id": "urn:asset" if case != "identity" else "urn:other"}})}}
    if case == "partial":
        row["g"] = uri("urn:asset")
    rows = [] if case == "missing" else [row]
    if case == "duplicate":
        rows.append(dict(row, version=version("3")))
    repository = native_repository(Session(rows))
    if case == "valid":
        docs, parts, v, token = repository.native_snapshot()
        assert docs == {"urn:asset": {"id": "urn:asset"}}
        assert set(parts) == {"urn:asset", "urn:product"}
        assert v == 2 and token == "a" * 32
    else:
        with pytest.raises(ValueError):
            repository.native_snapshot()


@pytest.mark.parametrize("case", ["committed", "not_committed", "wrong_token", "wrong_version"])
def test_ic12_durable_reconciliation(tmp_path, monkeypatch, case):
    path = tmp_path / "pending.sqlite"
    session = WriteSession(fail_write=True)
    def open_repository():
        return GraphDBRepository("http://graphdb/repositories/AAST",
            ["urn:asset", "urn:product"], session=session,
            native_mode=True, journal_path=path)
    repository = open_repository()
    docs = {"urn:asset": {"id": "urn:asset"}}
    parts = {"urn:asset": Graph(), "urn:product": Graph()}
    with pytest.raises(RepositoryUncertain):
        repository.compare_and_commit_native(1, Graph(), docs, parts)
    token, version_before = repository.pending_commit()
    assert token == session.token and version_before == 1
    repository._journal.close()
    recovered = open_repository()
    assert recovered.pending_commit() == (token, 1)
    with pytest.raises(RepositoryUncertain):
        recovered.compare_and_commit_native(1, Graph(), docs, parts)
    with pytest.raises(RepositoryUncertain):
        recovered.reconcile_pending()
    observed = 1 if case == "not_committed" else 3 if case == "wrong_version" else 2
    monkeypatch.setattr(recovered, "snapshot", lambda: (Graph(), observed))
    monkeypatch.setattr(recovered, "native_snapshot",
        lambda: (docs, parts, observed, "b" * 32 if case == "wrong_token" else token))
    if case in ("committed", "not_committed"):
        assert recovered.reconcile_pending(remote_quiescent=True) == case.upper()
        assert recovered.pending_commit() is None
    else:
        with pytest.raises(RepositoryUncertain):
            recovered.reconcile_pending(remote_quiescent=True)
        assert recovered.pending_commit() == (token, 1)
    assert len(session.updates) == 1
    recovered._journal.close()


def test_ic12_durable_confirmed_commit(tmp_path):
    session = WriteSession()
    repository = GraphDBRepository("http://graphdb/repositories/AAST",
        ["urn:asset", "urn:product"], session=session,
        native_mode=True, journal_path=tmp_path / "pending.sqlite")
    assert repository.compare_and_commit_native(1, Graph(),
        {"urn:asset": {"id": "urn:asset"}},
        {"urn:asset": Graph(), "urn:product": Graph()}) == (True, 2)
    assert repository.pending_commit() is None
    repository._journal.close()


@pytest.mark.parametrize("case", ["confirmed", "committed", "not_committed"])
def test_ic12_request_journal(tmp_path, monkeypatch, case):
    session = WriteSession(fail_write=case != "confirmed")
    path = tmp_path / "requests.sqlite"
    def open_repository():
        return GraphDBRepository("http://graphdb/repositories/AAST",
            ["urn:asset", "urn:product"], session=session,
            native_mode=True, journal_path=path)
    repository = open_repository()
    docs = {"urn:asset": {"id": "urn:asset"}}
    parts = {"urn:asset": Graph(), "urn:product": Graph()}
    response = {"message_id": "M1", "decision": "ACCEPTED", "repository_version": 2}
    repository.set_request_context("test", "M1", "fingerprint", response)
    if case == "confirmed":
        assert repository.compare_and_commit_native(1, Graph(), docs, parts) == (True, 2)
    else:
        with pytest.raises(RepositoryUncertain):
            repository.compare_and_commit_native(1, Graph(), docs, parts)
    repository.clear_request_context()
    repository._journal.close()
    recovered = open_repository()
    if case != "confirmed":
        assert recovered.request_outcome("test", "M1", "fingerprint") == {"pending": True}
        observed = 2 if case == "committed" else 1
        monkeypatch.setattr(recovered, "snapshot", lambda: (Graph(), observed))
        monkeypatch.setattr(recovered, "native_snapshot",
            lambda: (docs, parts, observed, session.token))
        assert recovered.reconcile_pending(remote_quiescent=True) == case.upper()
    if case == "not_committed":
        assert recovered.request_outcome("test", "M1", "fingerprint") is None
    else:
        assert recovered.request_outcome("test", "M1", "fingerprint") == response
        with pytest.raises(ValueError, match="Conflicting"):
            recovered.request_outcome("test", "M1", "different")
    assert recovered.request_outcome("other", "M1", "different") is None
    assert len(session.updates) == 1
    recovered._journal.close()


def test_ic12_rdf11_string_equivalence():
    from rdflib import Literal, URIRef
    from rdflib.namespace import XSD
    from selira.runtime.graphdb_repository import rdf11_triples
    s, p = URIRef("urn:s"), URIRef("urn:p")
    def terms(o):
        return rdf11_triples([(s, p, o)])
    assert terms(Literal("abc")) == terms(Literal("abc", datatype=XSD.string))
    assert terms(Literal("abc")) != terms(Literal("abc", lang="en"))
    assert terms(Literal("abc")) != terms(Literal("ABC"))
    assert terms(Literal("1")) != terms(Literal("1", datatype=XSD.integer))
    assert terms(Literal("urn:x")) != terms(URIRef("urn:x"))
