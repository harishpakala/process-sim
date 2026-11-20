"""Experimental deterministic N-domain SPARQL SELECT compiler.

Compiles only independently validated SHACL-qualified selections. NodeShape
URIs are NOT assumed to be rdf:type classes. No execution or graph inference.
"""
from __future__ import annotations

import re

from process_sim.dtwise.experimental_shacl_n_domain_selection import validate_n_domain_selection
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
_IRI = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>"{}|^`\\]+$')


def _iri(value: str) -> str:
    if not isinstance(value, str) or not _IRI.fullmatch(value):
        raise SelectionContractError("Invalid RDF predicate IRI in qualified registry")
    return f"<{value}>"


def compile_n_domain_sparql(selection: dict, prepared: dict) -> str:
    """Produce a read-only SELECT from the original, validated registry.

    Each domain must have exactly one selected identifier path in this initial
    compiler. This avoids choosing among multiple owners/paths implicitly.
    Every selected mapping is enforced; no spanning-tree optimization.
    SHACL NodeShape identifiers are metadata, not asserted rdf:type classes.
    """
    checked = validate_n_domain_selection(selection, prepared)
    if checked["status"] != "selected":
        raise SelectionContractError("Only selected plans can be compiled")

    registry = prepared["result_registry"]
    prompt = prepared["prompt"]
    identifiers = {c["id"]: c for c in prompt["identifier_path_candidates"]}
    mappings = {c["id"]: c for c in prompt["mapping_candidates"]}
    by_domain = {}
    for cid in checked["identifier_path_ids"]:
        entry = registry[cid]
        domain = entry["domain"]
        if domain in by_domain:
            raise SelectionContractError("Compiler requires one identifier path per domain")
        if entry["kind"] != "property":
            raise SelectionContractError("Identifier must be a property path")
        by_domain[domain] = cid

    # A shape is not a class. Generate only verified RDF predicates, and
    # preserve the same subject variable for shared path prefixes.
    variables = {}
    triples = []
    seen_triples = set()
    counter = 0

    def node_var(domain: str, nodes: list[str], index: int) -> str:
        nonlocal counter
        key = (domain, tuple(nodes[:index + 1]))
        if key not in variables:
            counter += 1
            variables[key] = f"?n{counter}"
        return variables[key]

    def add_triple(subject: str, predicate: str, obj: str) -> None:
        triple = f"{subject} {_iri(predicate)} {obj} ."
        if triple not in seen_triples:
            triples.append(triple)
            seen_triples.add(triple)

    def emit_path(cid: str, *, identifier: bool) -> str:
        nonlocal counter
        entry = registry[cid]
        nodes, edges = entry["node_uris"], entry["edges"]
        if not nodes or len(edges) != len(nodes) - 1:
            raise SelectionContractError("Malformed qualified path")
        for i, edge in enumerate(edges):
            if edge["from"] != nodes[i] or edge["to"] != nodes[i + 1]:
                raise SelectionContractError("Unverified path continuity")
            add_triple(node_var(entry["domain"], nodes, i),
                       edge["predicate"],
                       node_var(entry["domain"], nodes, i + 1))
        owner = node_var(entry["domain"], nodes, len(nodes) - 1)
        if entry["kind"] == "result":
            if identifier:
                raise SelectionContractError("Identifier must end in a property")
            return owner
        if entry["kind"] != "property" or not isinstance(entry.get("property"), dict):
            raise SelectionContractError("Unknown qualified result kind")
        if entry["property"]["owner"] != nodes[-1]:
            raise SelectionContractError("Property owner differs from path")
        counter += 1
        value = f"?v{counter}"
        add_triple(owner, entry["property"]["predicate"], value)
        return value

    # Emit identifier paths first; their bound values are the join operands.
    id_values = {cid: emit_path(cid, identifier=True)
                 for cid in checked["identifier_path_ids"]}
    projections = [emit_path(cid, identifier=False)
                   for cid in checked["result_ids"]]
    if len(set(projections)) != len(projections):
        raise SelectionContractError("Duplicate projected variable")

    filters = []
    for mid in checked["mapping_ids"]:
        edge = mappings[mid]
        left, right = edge["left_domain"], edge["right_domain"]
        if left not in by_domain or right not in by_domain:
            raise SelectionContractError("Missing selected mapping endpoint")
        lid, rid = by_domain[left], by_domain[right]
        if (lid not in edge["left_identifier_candidate_ids"]
                or rid not in edge["right_identifier_candidate_ids"]
                or not any(a["left_id"] == lid and a["right_id"] == rid
                           for a in edge["join_alternatives"])
                or identifiers[lid]["predicate"] != edge["left_property"]
                or identifiers[rid]["predicate"] != edge["right_property"]):
            raise SelectionContractError("Selected mapping endpoints are not approved")
        filters.append(f"FILTER({id_values[lid]} = {id_values[rid]})")

    if not triples or not filters:
        raise SelectionContractError("No supported RDF patterns for selected plan")
    body = "\n".join("  " + line for line in [*triples, *filters])
    return f"SELECT DISTINCT {' '.join(projections)} WHERE {{\n{body}\n}}"
