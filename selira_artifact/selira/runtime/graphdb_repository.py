"""GraphDB adapter with guarded atomic SPARQL updates for an exclusive writer."""
import re
import json
from threading import RLock
from uuid import uuid4

from rdflib import Graph, URIRef, Literal, BNode
from rdflib.namespace import XSD


def _iri(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\x00-\x1f{}|^\x60\\\"]+", value):
        raise ValueError("Expected absolute safe graph IRI")
    return URIRef(value).n3()


class GraphDBRepository:
    def __init__(self, endpoint, graph_iris, *, metadata_graph="urn:selira:repository:metadata",
                 session=None, timeout=60, partition=None, native_mode=False):
        self._native_mode = native_mode
        self._partition = partition
        self._lock = RLock()
        self._uncertain = False
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
        if self._native_mode:
            raise ValueError('RDF-only writes disabled in native mode')
        return self._commit(expected_version, graph)

    def compare_and_commit_native(self, expected_version, graph, documents, parts):
        if not self._native_mode:
            raise ValueError('Native mode required')
        if not documents or any(key != doc.get('id') for key, doc in documents.items()):
            raise ValueError('Invalid native document identities')
        native = Literal(json.dumps(documents, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return self._commit(expected_version, graph, parts=parts, native=native)

    def _commit(self, expected_version, graph, *, parts=None, native=None):
        if parts is None and self._partition is None:
            raise NotImplementedError("Explicit named graph partition required")
        with self._lock:
            if self._uncertain:
                raise RepositoryUncertain("Previous commit requires reconciliation")
            _, version = self.snapshot()
            if version != expected_version:
                return False, version
            parts = {_iri(k): v for k, v in (self._partition(graph) if parts is None else parts).items()}
            if set(parts) != set(self._graphs):
                raise ValueError("Partition must cover exactly the governed graphs")
            if set().union(*(set(g) for g in parts.values())) != set(graph):
                raise ValueError("Partition does not reproduce candidate")
            for g in parts.values():
                for s, p, o in g:
                    if not isinstance(s, URIRef) or not isinstance(p, URIRef) or not isinstance(o, (URIRef, Literal)):
                        raise ValueError("Writes require ground RDF triples")
                    for term in (s, p, o):
                        if isinstance(term, URIRef):
                            _iri(str(term))
            token = uuid4().hex
            old = Literal(version, datatype=XSD.integer).n3()
            new = Literal(version + 1, datatype=XSD.integer).n3()
            subject = "<urn:selira:repository>"
            vp = "<urn:selira:version>"
            cp = "<urn:selira:commitToken>"
            deletes = " ".join(f"GRAPH {g} {{ ?s{i} ?p{i} ?o{i} }}" for i,g in enumerate(self._graphs))
            # Separate OPTIONAL patterns would create a Cartesian product.
            # UNION selects one graph's old triples per solution instead.
            branches = " UNION ".join(f"{{ GRAPH {g} {{ ?s{i} ?p{i} ?o{i} }} }}" for i,g in enumerate(self._graphs))
            inserts = " ".join(f"GRAPH {g} {{ " + " ".join(
                f"{s.n3()} {p.n3()} {o.n3()} ." for s,p,o in triples) + " }"
                for g,triples in parts.items())
            native_graph = "<urn:selira:repository:native>"
            if native_graph in self._graphs or native_graph == self._metadata:
                raise ValueError("Native graph must be reserved")
            native_delete = f"GRAPH {native_graph} {{ {subject} <urn:selira:documents> ?oldDocuments }}" if native is not None else ""
            native_insert = f"GRAPH {native_graph} {{ {subject} <urn:selira:documents> {native.n3()} }}" if native is not None else ""
            native_where = f"OPTIONAL {{ {native_delete} }}" if native is not None else ""
            query = f"""
DELETE {{ GRAPH {self._metadata} {{ {subject} {vp} {old} . {subject} {cp} ?previous . }} {deletes} {native_delete} }}
INSERT {{ GRAPH {self._metadata} {{ {subject} {vp} {new} . {subject} {cp} "{token}" . }} {inserts} {native_insert} }}
WHERE {{
 GRAPH {self._metadata} {{ {subject} {vp} {old} .
 OPTIONAL {{ {subject} {cp} ?previous }} }}
 FILTER NOT EXISTS {{ GRAPH {self._metadata} {{ {subject} {vp} ?other FILTER(!sameTerm(?other, {old})) }} }}
 {native_where}
 OPTIONAL {{ {branches} }}
}}
"""
            try:
                response = self._session.post(self._endpoint + "/statements",
                    data=query.encode("utf-8"), headers={"Content-Type": "application/sparql-update"},
                    timeout=self._timeout)
                response.raise_for_status()
                check = self._session.post(self._endpoint,
                    data={"query": f"SELECT ?token WHERE {{ GRAPH {self._metadata} {{ {subject} {vp} {new} ; {cp} ?token }} }}", "infer": "false"},
                    headers={"Accept": "application/sparql-results+json"}, timeout=self._timeout)
                check.raise_for_status()
                rows = check.json()["results"]["bindings"]
                if len(rows) == 1 and rows[0]["token"]["value"] == token:
                    return True, version + 1
                raise RepositoryUncertain("Commit token not confirmed")
            except Exception as exc:
                self._uncertain = True
                raise RepositoryUncertain("Commit outcome unresolved; stop writes") from exc


class RepositoryUncertain(RuntimeError):
    """Do not retry automatically: the remote update may have committed."""



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
