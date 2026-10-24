#!/usr/bin/env python3
"""Step 7B: read-only entity-level cross-domain RDF relationship audit.

Conservative: exact identifiers are candidates, not automatically verified joins.
Ignores rdf:type, schema and annotation links as engineering integrations.
"""
import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

from ask_graphdb_ollama import graphdb_select

DOMAINS = {
    "AssetInventory": ("tep-asset-inventory", "assetinventory"),
    "ProductCatalog": ("tep-product-catalog", "productcatalog"),
    "EngineeringBOM": ("tep-engineering-bom", "engineeringbom"),
    "ECAD": ("tep-ecad", "/ecad/"),
    "OPCUA": ("tep-opcua-connectivity", "opcuaconnectivity"),
    "DEXPI": ("tep-dexpi", "/dexpi/"),
}
PAIRS = [
    ("AssetInventory", "ProductCatalog"),
    ("AssetInventory", "EngineeringBOM"),
    ("EngineeringBOM", "ECAD"),
    ("AssetInventory", "OPCUA"),
    ("DEXPI", "AssetInventory"),
]
IGNORE_PREDICATES = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2000/01/rdf-schema#domain",
    "http://www.w3.org/2000/01/rdf-schema#range",
    "http://www.w3.org/2002/07/owl#sameAs",
}
IDENTIFIER_TERMS = ("assetid", "equipmentid", "equipmenttag", "tagname", "assetidentifier",
                    "equipmentidentifier", "componentid", "referencedasset", "operationalreference",
                    "productreference", "candidateproductreference")
GENERIC_VALUES = {"asset", "equipment", "unknown", "none", "null", "true", "false"}


def domain(uri):
    u = uri.casefold()
    # Native AAS instance nodes have base64-encoded submodel IDs in their URI.
    if u.startswith("http://org.example.com/"):
        import base64
        segment = u.split("/", 4)[3]
        try:
            decoded = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)).decode("utf-8").casefold()
            u += " " + decoded
        except (ValueError, UnicodeError):
            pass
    for name, needles in DOMAINS.items():
        if any(needle in u for needle in needles):
            return name
    return None


def local_name(uri):
    return re.split(r"[/#]", uri)[-1].casefold()


def collect(rows):
    subjects = collections.defaultdict(set)
    iri_edges = collections.defaultdict(list)
    ids = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        s, p, o = row["s"], row["p"], row["o"]
        sd = domain(s)
        if not sd:
            continue
        subjects[sd].add(s)
        if row.get("oIsIRI") == "true":
            od = domain(o)
            if od and od != sd and p not in IGNORE_PREDICATES:
                iri_edges[(sd, od)].append({"subject": s, "predicate": p, "object": o})
        elif any(term in local_name(p) for term in IDENTIFIER_TERMS):
            v = o.strip().casefold()
            if v and v not in GENERIC_VALUES and len(v) <= 160:
                ids[sd][v].append({"subject": s, "predicate": p, "value": o})
    return subjects, iri_edges, ids


def evaluate(rows):
    subjects, edges, ids = collect(rows)
    results = []
    for left, right in PAIRS:
        explicit = edges.get((left, right), []) + edges.get((right, left), [])
        shared = sorted(set(ids[left]) & set(ids[right]))
        matches = []
        for value in shared:
            a, b = ids[left][value], ids[right][value]
            if any(x["subject"] != y["subject"] for x in a for y in b):
                matches.append({"identifier": value, "left": a[:2], "right": b[:2]})
        results.append({
            "path": left + " <-> " + right,
            "left_subject_count": len(subjects[left]),
            "right_subject_count": len(subjects[right]),
            "explicit_cross_domain_edges": len(explicit),
            "explicit_edge_examples": explicit[:5],
            "exact_identifier_match_groups": len(matches),
            "identifier_match_examples": matches[:10],
            "classification": ("EXPLICIT_RDF_EDGE" if explicit else
                               "POTENTIAL_IDENTIFIER_JOIN_REQUIRES_VERIFICATION" if matches else
                               "NOT_ESTABLISHED"),
            "caution": "An explicit RDF edge requires predicate-level semantic review; matching strings are not verified engineering identity.",
        })
    return {
        "rows_scanned": len(rows),
        "possibly_truncated": False,
        "domains": {k: len(subjects[k]) for k in DOMAINS},
        "paths": results,
        "limitations": [
            "Only selected known identifier predicates are compared.",
            "Native AAS structural parent-child nodes can obscure logical cross-domain identifiers.",
            "Cross-domain predicates and identifier matches require human semantic validation.",
            "No inference of installed equipment, operational safety, or engineering approval.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv("GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--output", type=Path, default=Path("reports/cross_domain_entity_links.json"))
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000000:
        parser.error("--limit must be between 1 and 1000000")
    query = ('SELECT ?s ?p ?o (IF(isIRI(?o), "true", "false") AS ?oIsIRI) '
             'WHERE { ?s ?p ?o . FILTER(isIRI(?s) && isIRI(?p)) } LIMIT %d' % args.limit)
    try:
        rows = graphdb_select(args.graphdb, query)
        report = evaluate(rows)
        report["possibly_truncated"] = len(rows) >= args.limit
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as exc:
        print("Audit failed:", exc, file=sys.stderr)
        return 1
    print("Triples scanned:", report["rows_scanned"])
    print("Potential truncation:", report["possibly_truncated"])
    print("Domain subject counts:", report["domains"])
    for path in report["paths"]:
        print("\n" + path["path"])
        print("  Classification:", path["classification"])
        print("  Explicit RDF edges:", path["explicit_cross_domain_edges"])
        print("  Exact identifier match groups:", path["exact_identifier_match_groups"])
        for match in path["identifier_match_examples"][:3]:
            print("  Candidate shared identifier:", match["identifier"])
    print("\nReport:", args.output)
    print("WARNING: This is a discovery audit, not proof of engineering equivalence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
