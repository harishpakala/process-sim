"""Build a deterministic schema-aware search index from DTWise TTL catalogs.

The index describes schema evidence, not instance data or inferred joins.
Run: python -m semantic.dtwise_schema_index
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, SH

DT = Namespace("https://example.org/dtwise/")
GENERIC = {"https://example.org/aas/SMC", "https://example.org/aas/Submodel"}


def tokens(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    return sorted(set(re.findall(r"[a-z0-9]+", value.lower())))


def name(uri):
    return re.split(r"[/#]", str(uri))[-1]


def values(graph, subject, predicate):
    return sorted(set(str(x) for x in graph.objects(subject, predicate)))


def build_index(directory):
    directory = Path(directory)
    c, r = Graph(), Graph()
    c.parse(directory / "dtwise-concepts.ttl", format="turtle")
    r.parse(directory / "dtwise-relationships.ttl", format="turtle")

    concepts = []
    for record in set(c.subjects(RDF.type, DT.ConceptRecord)):
        uri = c.value(record, DT.refersTo)
        if not isinstance(uri, URIRef):
            continue
        domains = values(c, record, DT.sourceDomain)
        labels = sorted(set(values(c, record, RDFS.label) + values(c, record, SH.name)))
        descriptions = sorted(set(values(c, record, RDFS.comment) + values(c, record, SH.description)))
        types = values(c, record, DT.sourceType)
        concepts.append({
            "id": str(record), "uri": str(uri), "domain": domains[0] if domains else "",
            "labels": labels, "descriptions": descriptions, "types": types,
            "kind": ("shape" if str(SH.NodeShape) in types or str(SH.PropertyShape) in types
                     else "class" if str(OWL.Class) in types or str(RDFS.Class) in types
                     else "property" if any(x in types for x in
                          (str(OWL.ObjectProperty), str(OWL.DatatypeProperty), str(RDF.Property)))
                     else "reference"),
        })
    concepts.sort(key=lambda x: (x["domain"], x["uri"], x["id"]))

    relationships = []
    for record in set(r.subjects(RDF.type, DT.RelationshipRecord)):
        subject = r.value(record, DT.subject)
        predicate = r.value(record, DT.predicate)
        obj = r.value(record, DT.object)
        if not all(isinstance(x, URIRef) for x in (subject, predicate, obj)):
            continue
        domains = values(r, record, DT.sourceDomain)
        relationships.append({
            "id": str(record), "domain": domains[0] if domains else "",
            "subject": str(subject), "predicate": str(predicate),
            "object": str(obj), "evidence": str(r.value(record, DT.evidenceKind) or ""),
        })
    relationships.sort(key=lambda x: (x["domain"], x["subject"], x["predicate"], x["object"]))

    postings = defaultdict(list)
    for i, item in enumerate(concepts):
        search_text = " ".join([name(item["uri"]), *item["labels"], *item["descriptions"]])
        for token in tokens(search_text):
            postings[token].append(i)

    # A SHACL path is usable only in context: NodeShape --sh:property-->
    # PropertyShape --sh:path--> predicate. These are schema declarations,
    # not instance triple patterns or cross-domain joins.
    by_subject = defaultdict(list)
    for edge in relationships:
        by_subject[(edge["domain"], edge["subject"])].append(edge)

    shape_paths = []
    for edge in relationships:
        if edge["predicate"] != str(SH.property):
            continue
        for child in by_subject.get((edge["domain"], edge["object"]), []):
            if child["predicate"] == str(SH.path):
                shape_paths.append({
                    "domain": edge["domain"], "node_shape": edge["subject"],
                    "property_shape": edge["object"], "path": child["object"],
                    "evidence": [edge["id"], child["id"]],
                })
    shape_paths.sort(key=lambda x: (x["domain"], x["node_shape"], x["path"], x["property_shape"]))

    # Keep potentially useful schema edges; never turn shared aas:SMC
    # or same-named identifier properties into verified mappings.
    semantic_predicates = {str(RDFS.domain), str(RDFS.range), str(RDFS.subClassOf),
                           str(OWL.equivalentClass), str(OWL.equivalentProperty)}
    ontology_edges = [x for x in relationships if x["predicate"] in semantic_predicates]
    generic_edges = [x for x in relationships if x["object"] in GENERIC]
    result = {
        "version": 1,
        "sources": ["dtwise-concepts.ttl", "dtwise-relationships.ttl"],
        "concepts": concepts,
        "token_postings": {k: v for k, v in sorted(postings.items())},
        "relationships": relationships,
        "shape_paths": shape_paths,
        "ontology_edges": ontology_edges,
        "diagnostics": {
            "concept_count": len(concepts),
            "relationship_count": len(relationships),
            "shape_path_count": len(shape_paths),
            "ontology_edge_count": len(ontology_edges),
            "generic_aas_reference_count": len(generic_edges),
            "verified_cross_domain_mapping_count": 0,
            "mapping_note": "No verified mapping source was supplied; no joins inferred.",
        },
    }
    return result


def search(index, query, limit=15):
    """Rank global candidates by normalized token overlap; no LLM needed."""
    query_tokens = set(tokens(query))
    scores = defaultdict(int)
    for token in query_tokens:
        for i in index["token_postings"].get(token, []):
            scores[i] += 1
    ranked = sorted(scores, key=lambda i: (-scores[i], index["concepts"][i]["domain"],
                                            index["concepts"][i]["uri"]))
    return [{"score": scores[i], **index["concepts"][i]} for i in ranked[:limit]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("out/semantic/dtwise"))
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--query", help="Optional retrieval smoke test")
    args = parser.parse_args()
    index = build_index(args.directory)
    destination = args.output or args.directory / "dtwise-schema-index.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["diagnostics"], indent=2))
    print("Wrote:", destination)
    if args.query:
        for hit in search(index, args.query):
            print(hit["score"], hit["domain"], hit["kind"], hit["uri"])


if __name__ == "__main__":
    main()
