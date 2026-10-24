#!/usr/bin/env python3
"""Read-only Step 7A audit of RDF domains and cross-domain links in GraphDB.

Reports observed namespaces, classes, predicates, and explicit URI-to-URI edges.
Does not infer joins from similar names and does not write to the repository.
"""
import argparse
import collections
import json
import os
import sys
from pathlib import Path

from ask_graphdb_ollama import graphdb_select

QUERY = """
SELECT ?s ?p ?o WHERE {
  ?s ?p ?o .
  FILTER(isIRI(?s) && isIRI(?p))
} LIMIT 100000
"""
TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
OUT = Path("reports/cross_domain_graph_audit.json")


def namespace(uri):
    if "#" in uri:
        return uri.rsplit("#", 1)[0] + "#"
    return uri.rsplit("/", 1)[0] + "/" if "/" in uri else uri


def analyze(rows, cap):
    predicates = collections.Counter()
    classes = collections.Counter()
    namespaces = collections.Counter()
    links = collections.Counter()
    examples = {}
    subjects = set()
    for row in rows:
        s, p, o = row["s"], row["p"], row["o"]
        subjects.add(s)
        sn = namespace(s)
        namespaces[sn] += 1
        predicates[p] += 1
        if p == TYPE:
            classes[o] += 1
        # SPARQL JSON value is not enough to tell literal vs URI; request the
        # object's term type in the query and count only genuine IRI edges.
        if row.get("oIsIRI") == "true":
            on = namespace(o)
            links[(sn, p, on)] += 1
            examples.setdefault((sn, p, on), {"subject": s, "object": o})
    return {
        "triple_rows_scanned": len(rows),
        "query_limit": cap,
        "possibly_truncated": len(rows) >= cap,
        "distinct_subjects": len(subjects),
        "subject_namespaces": [{"namespace": k, "triples": v} for k, v in namespaces.most_common()],
        "rdf_classes": [{"class": k, "count": v} for k, v in classes.most_common()],
        "predicates": [{"predicate": k, "count": v} for k, v in predicates.most_common()],
        "iri_relationships": [
            {"from_namespace": a, "predicate": p, "to_namespace": b, "count": n,
             "example": examples[(a, p, b)]}
            for (a, p, b), n in links.most_common()
        ],
        "cross_namespace_iri_relationships": [
            {"from_namespace": a, "predicate": p, "to_namespace": b, "count": n,
             "example": examples[(a, p, b)]}
            for (a, p, b), n in links.most_common() if a != b
        ],
        "interpretation": "Namespace links are candidate domain connections, not proof of semantic engineering joins. Validate asset identifiers, predicates and provenance before reasoning."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv("GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000000:
        parser.error("--limit must be between 1 and 1000000")
    query = """
SELECT ?s ?p ?o (IF(isIRI(?o), "true", "false") AS ?oIsIRI)
WHERE { ?s ?p ?o . FILTER(isIRI(?s) && isIRI(?p)) }
LIMIT %d
""" % args.limit
    try:
        rows = graphdb_select(args.graphdb, query)
        report = analyze(rows, args.limit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 1
    print("RDF triples scanned:", report["triple_rows_scanned"])
    print("Distinct subjects:", report["distinct_subjects"])
    print("Subject namespaces:", len(report["subject_namespaces"]))
    print("RDF classes:", len(report["rdf_classes"]))
    print("Predicates:", len(report["predicates"]))
    print("Cross-namespace IRI relationship groups:", len(report["cross_namespace_iri_relationships"]))
    print("Potential truncation:", report["possibly_truncated"])
    print("Report:", args.output)
    print("\nTop subject namespaces:")
    for entry in report["subject_namespaces"][:12]:
        print(" ", entry["triples"], entry["namespace"])
    print("\nCross-namespace relationships:")
    for entry in report["cross_namespace_iri_relationships"][:30]:
        print(" ", entry["count"], entry["from_namespace"], "--", entry["predicate"], "-->", entry["to_namespace"])
    print("\nNOTE: This inventories RDF structure only; cross-domain reasoning capability is not yet verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
