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
