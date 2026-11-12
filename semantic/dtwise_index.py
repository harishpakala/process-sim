"""Deterministic DTWise catalog derived from lifted ontology and SHACL graphs.

This is metadata for discovery, not a new domain ontology or inferred mapping.
Existing domain IRIs remain unchanged. No identifier equivalence is asserted.
"""
from hashlib import sha256
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import SH

DT = Namespace("https://example.org/dtwise/")
CONCEPT_TYPES = (OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property, SH.NodeShape, SH.PropertyShape)
SEMANTIC_PREDICATES = (RDFS.subClassOf, RDFS.domain, RDFS.range, OWL.equivalentClass, OWL.equivalentProperty, SH.targetClass, SH.path, SH.node, SH["class"], SH.property)


def _record(kind, *parts):
    digest = sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()
    return DT[f"{kind}/{digest}"]


def _init_graph():
    graph = Graph()
    graph.bind("dtwise", DT)
    graph.bind("sh", SH)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    return graph


def build_dtwise_catalog(domain_graphs):
    """Return (concept_catalog, relationship_catalog) for (domain, Graph) pairs.

    Records reference source URIs and carry provenance. No owl:sameAs or
    cross-domain mappings are fabricated. SHACL constraints are kept separate
    from ontology declarations.
    """
    concepts, relationships = _init_graph(), _init_graph()
    for domain, source in sorted(domain_graphs, key=lambda pair: pair[0]):
        domain_name = Literal(domain)
        identified = set()
        for concept_type in CONCEPT_TYPES:
            identified.update(subject for subject in source.subjects(RDF.type, concept_type) if isinstance(subject, URIRef))
        identified.update(value for value in source.objects(None, SH.path) if isinstance(value, URIRef))
        identified.update(value for value in source.objects(None, SH.targetClass) if isinstance(value, URIRef))
        for uri in sorted(identified, key=str):
            record = _record("concept", domain, uri)
            concepts.add((record, RDF.type, DT.ConceptRecord))
            concepts.add((record, DT.sourceDomain, domain_name))
            concepts.add((record, DT.refersTo, uri))
            for concept_type in CONCEPT_TYPES:
                if (uri, RDF.type, concept_type) in source:
                    concepts.add((record, DT.sourceType, concept_type))
            for predicate in (RDFS.label, RDFS.comment, SH.name, SH.description):
                for value in source.objects(uri, predicate):
                    concepts.add((record, predicate, value))
        for subject, predicate, obj in sorted(source, key=lambda triple: tuple(map(str, triple))):
            if predicate not in SEMANTIC_PREDICATES or not isinstance(subject, URIRef):
                continue
            # Preserve URI-to-URI declarations. Complex SHACL paths and
            # literal constraints remain in the original SHACL source.
            if not isinstance(obj, URIRef):
                continue
            record = _record("relationship", domain, subject, predicate, obj)
            relationships.add((record, RDF.type, DT.RelationshipRecord))
            relationships.add((record, DT.sourceDomain, domain_name))
            relationships.add((record, DT.subject, subject))
            relationships.add((record, DT.predicate, predicate))
            relationships.add((record, DT.object, obj))
            relationships.add((record, DT.evidenceKind, Literal("shacl" if str(predicate).startswith(str(SH)) else "ontology")))
    return concepts, relationships


def write_dtwise_catalog(domain_graphs, output_directory):
    """Write two reproducible TTL metadata files; return their paths."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    concepts, relationships = build_dtwise_catalog(domain_graphs)
    paths = (directory / "dtwise-concepts.ttl", directory / "dtwise-relationships.ttl")
    for graph, path in zip((concepts, relationships), paths):
        graph.serialize(destination=str(path), format="turtle")
    return paths
