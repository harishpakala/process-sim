"""Deterministic, read-only SPARQL path compilation from verified SHACL candidates.

One SELECT per selected path: never infer joins between sibling branches.
SHACL NodeShape URIs are not assumed to be RDF classes.
"""
from __future__ import annotations

import re

from process_sim.dtwise.experimental_shacl_selection import validate_selection

_IRI = re.compile(r"^[^<>\x00-\x20\x7f]*$")


def _iri(value: str) -> str:
    if not isinstance(value, str) or not value or not _IRI.fullmatch(value):
        raise ValueError("Invalid IRI in verified SHACL metadata")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("Only absolute HTTP(S) predicate IRIs are supported")
    return "<" + value + ">"


def compile_selected_paths(prepared: dict, selection: dict) -> list[dict]:
    """Compile strictly validated selected IDs into separate SPARQL SELECTs.

    No execution, graph assumptions, cross-domain joins, or LLM-authored SPARQL.
    """
    validated = validate_selection(selection, prepared)
    if validated["status"] != "selected":
        return []
    compiled = []
    for candidate_id in validated["selected_candidate_ids"]:
        record = prepared["registry"][candidate_id]
        nodes = record["node_uris"]
        edges = record["edges"]
        prop = record["property"]
        if not nodes or len(edges) != len(nodes) - 1:
            raise ValueError("Candidate path has inconsistent node/edge count")
        if prop["owner"] != nodes[-1]:
            raise ValueError("Terminal property owner does not match path")
        triples = []
        for i, edge in enumerate(edges):
            if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
                raise ValueError("Candidate contains a disconnected or reversed edge")
            triples.append(f"  ?n{i} {_iri(edge['predicate'])} ?n{i + 1} .")
        triples.append(f"  ?n{len(nodes) - 1} {_iri(prop['predicate'])} ?value .")
        sparql = "SELECT DISTINCT ?value WHERE {\n" + "\n".join(triples) + "\n}"
        compiled.append({"candidate_id": candidate_id,
                         "path": next(c["path"] for c in prepared["prompt"]["candidates"]
                                      if c["id"] == candidate_id),
                         "sparql": sparql})
    return compiled
