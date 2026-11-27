"""Read-side GraphDB adapter; writes and initialization are deliberately absent."""
import re

from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import XSD


def _iri(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\x00-\x1f{}|^\x60\\\"]+", value):
        raise ValueError("Expected absolute safe graph IRI")
    return URIRef(value).n3()


class GraphDBRepository:
    def __init__(self, endpoint, graph_iris, *, metadata_graph="urn:selira:repository:metadata",
                 session=None, timeout=60):
        if session is None:
            import requests
            session = requests.Session()
        self._session = session
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout
        self._graphs = tuple(dict.fromkeys(_iri(g) for g in graph_iris))
        self._metadata = _iri(metadata_graph)
        if not self._graphs or self._metadata in self._graphs:
            raise ValueError("Expected nonempty governed graphs distinct from metadata")

    def snapshot(self):
        # One explicit-only SELECT; no default-union or inferred triples.
        query = f"""
SELECT ?version ?g ?s ?p ?o WHERE {{
  GRAPH {self._metadata} {{
    <urn:selira:repository> <urn:selira:version> ?version .
  }}
  OPTIONAL {{
    VALUES ?g {{ {' '.join(self._graphs)} }}
    GRAPH ?g {{ ?s ?p ?o }}
  }}
}}
"""
        response = self._session.post(
            self._endpoint, data={"query": query, "infer": "false"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=self._timeout)
        response.raise_for_status()
        rows = response.json()["results"]["bindings"]
        versions = set()
        graph = Graph()
        for row in rows:
            v = row["version"]
            if (v["type"] != "literal" or v.get("datatype") != str(XSD.integer)
                    or not re.fullmatch(r"0|[1-9][0-9]*", v["value"])):
                raise ValueError("Invalid repository version")
            versions.add(int(v["value"]))
            present = [k in row for k in ("g", "s", "p", "o")]
            if any(present):
                if not all(present) or _iri(row["g"]["value"]) not in self._graphs:
                    raise ValueError("Invalid governed graph result")
                s, p, o = (_term(row[k]) for k in ("s", "p", "o"))
                if not isinstance(s, (URIRef, BNode)) or not isinstance(p, URIRef):
                    raise ValueError("Invalid RDF triple")
                graph.add((s, p, o))
        if len(versions) != 1:
            raise ValueError("Missing or inconsistent repository version")
        return graph, versions.pop()

    def compare_and_commit(self, expected_version, graph):
        raise NotImplementedError("GraphDB writes require IC-12I.3")


def _term(binding):
    kind, value = binding["type"], binding["value"]
    if kind == "uri":
        _iri(value)
        return URIRef(value)
    if kind == "bnode":
        return BNode(value)
    if kind in ("literal", "typed-literal"):
        return Literal(value, lang=binding.get("xml:lang"),
                       datatype=binding.get("datatype"), normalize=False)
    raise ValueError("Unsupported RDF result term")
