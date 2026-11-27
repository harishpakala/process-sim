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
