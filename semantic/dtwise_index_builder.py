
"""Build a searchable JSON index from DTWise semantic TTL catalogs."""

import json
import re
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import SH

DT = Namespace("https://example.org/dtwise/")

INPUT_DIR = Path("out/semantic/dtwise")
OUTPUT_FILE = INPUT_DIR / "dtwise-index.json"


def tokenize(text):
    """Normalize identifiers such as hasAssetIdentifier."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return re.findall(r"[a-z0-9]+", text.lower())


def local_name(uri):
    return re.split(r"[/#]", str(uri))[-1]


def build_index():
    concepts_graph = Graph()
    relationships_graph = Graph()

    concepts_graph.parse(
        INPUT_DIR / "dtwise-concepts.ttl",
        format="turtle",
    )
    relationships_graph.parse(
        INPUT_DIR / "dtwise-relationships.ttl",
        format="turtle",
    )

    concepts = []
    relationships = []
    inverted_index = defaultdict(set)

    for record in concepts_graph.subjects(RDF.type, DT.ConceptRecord):
        uri = concepts_graph.value(record, DT.refersTo)
        domain = concepts_graph.value(record, DT.sourceDomain)

        if not isinstance(uri, URIRef):
            continue

        labels = [
            str(value)
            for predicate in (RDFS.label, SH.name)
            for value in concepts_graph.objects(record, predicate)
        ]

        descriptions = [
            str(value)
            for predicate in (RDFS.comment, SH.description)
            for value in concepts_graph.objects(record, predicate)
        ]

        concept = {
            "uri": str(uri),
            "domain": str(domain or ""),
            "types": sorted(
                str(value)
                for value in concepts_graph.objects(record, DT.sourceType)
            ),
            "labels": sorted(set(labels)),
            "descriptions": sorted(set(descriptions)),
        }

        concept_id = len(concepts)
        concepts.append(concept)

        searchable = " ".join([
            local_name(uri),
            *labels,
            *descriptions,
        ])

        for token in tokenize(searchable):
            inverted_index[token].add(concept_id)

    for record in relationships_graph.subjects(
        RDF.type, DT.RelationshipRecord
    ):
        relationships.append({
            "domain": str(
                relationships_graph.value(record, DT.sourceDomain) or ""
            ),
            "subject": str(
                relationships_graph.value(record, DT.subject) or ""
            ),
            "predicate": str(
                relationships_graph.value(record, DT.predicate) or ""
            ),
            "object": str(
                relationships_graph.value(record, DT.object) or ""
            ),
            "evidence": str(
                relationships_graph.value(record, DT.evidenceKind) or ""
            ),
        })

    concepts.sort(key=lambda c: (c["domain"], c["uri"]))
    relationships.sort(
        key=lambda r: (
            r["domain"], r["subject"], r["predicate"], r["object"]
        )
    )

    # Rebuild token postings after sorting concept records.
    inverted_index = defaultdict(set)

    for concept_id, concept in enumerate(concepts):
        searchable = " ".join([
            local_name(concept["uri"]),
            *concept["labels"],
            *concept["descriptions"],
        ])
        for token in tokenize(searchable):
            inverted_index[token].add(concept_id)

    index = {
        "schema_version": "1.0",
        "concepts": concepts,
        "relationships": relationships,
        "tokens": {
            token: sorted(ids)
            for token, ids in sorted(inverted_index.items())
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("DTWise index generated")
    print("Concepts:", len(concepts))
    print("Relationships:", len(relationships))
    print("Search tokens:", len(inverted_index))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    build_index()
