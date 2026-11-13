
from pathlib import Path
from collections import Counter
from rdflib import Graph, Namespace, RDF, RDFS
from rdflib.namespace import SH

DT = Namespace("https://example.org/dtwise/")

ROOT = Path("semantic//ontology/dtwise")
concept_file = ROOT / "dtwise-concepts.ttl"
relationship_file = ROOT / "dtwise-relationships.ttl"

concepts = Graph()
relationships = Graph()

concepts.parse(concept_file, format="turtle")
relationships.parse(relationship_file, format="turtle")

print("\n=== 1. CATALOG STATISTICS ===")
print("Concept triples:", len(concepts))
print("Relationship triples:", len(relationships))

records = list(concepts.subjects(RDF.type, DT.ConceptRecord))
edges = list(relationships.subjects(RDF.type, DT.RelationshipRecord))

print("Concept records:", len(records))
print("Relationship records:", len(edges))

print("\n=== 2. DOMAIN COVERAGE ===")
counts = Counter(
    str(domain)
    for record in records
    for domain in concepts.objects(record, DT.sourceDomain)
)

for domain, count in sorted(counts.items()):
    print(f"{domain}: {count} concepts")

print("\n=== 3. CONCEPT DISCOVERY ===")

keywords = [
    "reactor",
    "instrument",
    "pressure",
    "flow",
    "temperature",
    "level",
    "device",
    "localid",
    "assetidentifier",
]

for keyword in keywords:
    matches = []

    for record in records:
        uri = concepts.value(record, DT.refersTo)
        domain = concepts.value(record, DT.sourceDomain)

        labels = [
            str(v)
            for predicate in (RDFS.label, SH.name, RDFS.comment, SH.description)
            for v in concepts.objects(record, predicate)
        ]

        searchable = " ".join([str(uri or ""), *labels]).lower()

        if keyword.lower() in searchable:
            matches.append((str(domain), str(uri)))

    print(f"\n[{keyword}] {len(matches)} matches")
    for domain, uri in matches[:15]:
        print(f"  {domain}: {uri}")

print("\n=== 4. RELATIONSHIP DISCOVERY ===")

for record in edges:
    domain = relationships.value(record, DT.sourceDomain)
    subject = relationships.value(record, DT.subject)
    predicate = relationships.value(record, DT.predicate)
    obj = relationships.value(record, DT.object)

    searchable = f"{subject} {predicate} {obj}".lower()

    if any(
        keyword in searchable
        for keyword in ("reactor", "instrument", "localid", "assetidentifier")
    ):
        print(f"\nDomain: {domain}")
        print("Subject:", subject)
        print("Predicate:", predicate)
        print("Object:", obj)

print("\n=== 5. CROSS-DOMAIN RELATIONSHIPS ===")

# Detect whether relationship endpoints refer to concepts
# cataloged under different domain names.
uri_domains = {}

for record in records:
    uri = concepts.value(record, DT.refersTo)
    domain = concepts.value(record, DT.sourceDomain)
    if uri is not None and domain is not None:
        uri_domains.setdefault(uri, set()).add(str(domain))

cross_domain = []

for record in edges:
    subject = relationships.value(record, DT.subject)
    obj = relationships.value(record, DT.object)

    left_domains = uri_domains.get(subject, set())
    right_domains = uri_domains.get(obj, set())

    for left in left_domains:
        for right in right_domains:
            if left != right:
                cross_domain.append((left, right, subject, obj))

print("Cross-domain candidate relationships:", len(cross_domain))

for left, right, subject, obj in cross_domain[:20]:
    print(f"{left} -> {right}: {subject} -> {obj}")

print("\nVALIDATION COMPLETE")
