#!/usr/bin/env python3
"""Phase 6D: read-only GraphDB predicate and identifier evidence probes.

This is an observation tool, NOT an identity verifier. Equal literal identifiers
are candidates only; neither equality nor functional association proves physical
membership, installation, or BOM occurrence.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from experiments.q13_extract_focused_schema import ROOT, extract
except ModuleNotFoundError as exc:
    if exc.name != "experiments":
        raise
    from q13_extract_focused_schema import ROOT, extract

PREDICATES = (
    "https://example.org/ecad/hasPLCEndPoint",
    "https://example.org/ecad/hasAssetIdentifier",
    "https://example.org/dexpi/hasAssetIdentifier",
    "https://example.org/assetinventory/hasAssetIdentifier",
    "https://example.org/engineeringbom/hasAssetIdentifier",
    "https://example.org/opcuaconnectivity/hasAssetIdentifier",
    "https://example.org/productcatalog/hasIRDI",
    "https://example.org/productcatalog/hasQuDTAttribute",
    "https://example.org/productcatalog/hasCatalogTechnicalSpecification",
    "https://example.org/productcatalog/hasCrossDomainAssociationEvidence",
    "https://example.org/productcatalog/hasECLASSIRDI",
    "https://example.org/productcatalog/hasECLASSClass",
    "https://example.org/productcatalog/hasTechnicalProperty",
    "https://example.org/productcatalog/hasTechnicalProperties",
    "https://example.org/productcatalog/hasProductIdentifier",
    "https://example.org/assetinventory/hasProductIdentifier",
    "https://example.org/engineeringbom/hasProductIdentifier",
)
IDENTIFIER_FAMILIES = {
    "asset_identifier": [
        p for p in PREDICATES if p.endswith("/hasAssetIdentifier")
    ],
    "product_identifier": [
        p for p in PREDICATES if p.endswith("/hasProductIdentifier")
    ],
}


def iri(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
        c in value for c in "<>\\\"{}|^\x00\n\r"
    ):
        raise ValueError("Unsafe predicate IRI")
    return "<" + value + ">"


def sparql_select(endpoint, query, timeout):
    response = requests.post(
        endpoint, data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {key: value.get("value") for key, value in row.items()}
        for row in data["results"]["bindings"]
    ]


def probe_predicate(endpoint, predicate, timeout):
    # No GRAPH clause: GraphDB default dataset behavior is endpoint-dependent.
    query = "SELECT (COUNT(*) AS ?count) WHERE { ?s " + iri(predicate) + " ?o . }"
    rows = sparql_select(endpoint, query, timeout)
    return {"predicate": predicate, "triple_count": int(rows[0]["count"])}


def probe_identifier_overlap(endpoint, left, right, timeout, limit):
    # A matching RDF literal is only a value-equality hypothesis. No join is
    # authorized for production compilation by these observations.
    query = (
        "SELECT ?identifier (COUNT(DISTINCT ?a) AS ?leftResources) "
        "(COUNT(DISTINCT ?b) AS ?rightResources) WHERE { "
        "?a " + iri(left) + " ?identifier . "
        "?b " + iri(right) + " ?identifier . "
        "FILTER(isLiteral(?identifier)) "
        "} GROUP BY ?identifier ORDER BY STR(?identifier) LIMIT " + str(limit)
    )
    return sparql_select(endpoint, query, timeout)


def collect(endpoint, timeout=20, sample_limit=10):
    if sample_limit < 1 or sample_limit > 100:
        raise ValueError("sample_limit must be between 1 and 100")
    schema = extract()
    declared = {
        prop["predicate"]
        for domain in schema["domains"]
        for shape in domain["node_shapes"]
        for prop in shape["properties"]
    }
    probes = []
    for predicate in PREDICATES:
        item = {"predicate": predicate, "declared_in_extracted_shacl": predicate in declared}
        try:
            item.update(probe_predicate(endpoint, predicate, timeout))
            item["probe_status"] = "ok"
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            item["probe_status"] = "error"
            item["error"] = str(exc)
        probes.append(item)
    overlaps = []
    for family, predicates in IDENTIFIER_FAMILIES.items():
        for i, left in enumerate(predicates):
            for right in predicates[i + 1:]:
                item = {"family": family, "left_predicate": left, "right_predicate": right,
                        "semantics": "literal_value_equality_only_not_verified_identity"}
                try:
                    item["sample_matches"] = probe_identifier_overlap(
                        endpoint, left, right, timeout, sample_limit)
                    item["probe_status"] = "ok"
                except (requests.RequestException, ValueError, KeyError) as exc:
                    item["probe_status"] = "error"
                    item["error"] = str(exc)
                item["identity_verified"] = False
                item["physical_membership_verified"] = False
                overlaps.append(item)
    return {
        "method": "phase6d_read_only_graphdb_observation",
        "endpoint": endpoint,
        "predicate_probes": probes,
        "identifier_overlap_samples": overlaps,
        "limitations": [
            "Counts depend on GraphDB repository default dataset and inference configuration.",
            "Matching literals are not verified cross-domain identity.",
            "Absence of a triple in the queried dataset is not proof of global absence.",
            "No physical membership, installation, or BOM occurrence is inferred.",
            "No query-plan repairs or GraphDB updates are performed.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--output", type=Path,
                        default=Path("reports/phase6_instance_evidence.json"))
    args = parser.parse_args()
    result = collect(args.graphdb_url, args.timeout, args.sample_limit)
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Report:", path)
    for probe in result["predicate_probes"]:
        print(probe["predicate"], probe.get("triple_count", probe.get("error")))
    print("Identifier overlap comparisons:", len(result["identifier_overlap_samples"]))
    return 1 if any(x["probe_status"] == "error" for x in (
        result["predicate_probes"] + result["identifier_overlap_samples"])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
