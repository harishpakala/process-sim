#!/usr/bin/env python3
"""Phase 6E: read-only, resource-level RDF evidence inspection.

Observed triples are distinguished from identifier-value overlap. No asserted
physical containment, installation, BOM membership, or cross-domain identity
is inferred from matching identifiers or recorded parent context.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from experiments.q13_extract_focused_schema import ROOT
except ModuleNotFoundError as exc:
    if exc.name != "experiments":
        raise
    from q13_extract_focused_schema import ROOT

ASSET_IDS = (
    "https://aas.example.com/FI106",
    "https://aas.example.com/CV1201",
)
PRODUCT_IDS = (
    "https://example.org/product-types/EandH_Promass_F300_Candidate",
    "https://example.org/product-types/SAMSON_3241_7",
)
PREDICATES = {
    "ecad_asset": "https://example.org/ecad/hasAssetIdentifier",
    "dexpi_asset": "https://example.org/dexpi/hasAssetIdentifier",
    "inventory_asset": "https://example.org/assetinventory/hasAssetIdentifier",
    "bom_asset": "https://example.org/engineeringbom/hasAssetIdentifier",
    "opc_asset": "https://example.org/opcuaconnectivity/hasAssetIdentifier",
    "catalog_product": "https://example.org/productcatalog/hasProductIdentifier",
    "inventory_product": "https://example.org/assetinventory/hasProductIdentifier",
    "bom_product": "https://example.org/engineeringbom/hasProductIdentifier",
}
DETAIL_PREDICATES = (
    "https://example.org/ecad/hasPLCEndPoint",
    "https://example.org/productcatalog/hasTechnicalProperties",
    "https://example.org/productcatalog/hasECLASSIRDI",
    "https://example.org/productcatalog/hasECLASSClass",
)


def safe_iri(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
        c in value for c in '<>\\\"{}|^\x00\r\n'
    ):
        raise ValueError("Unsafe IRI")
    return "<" + value + ">"


def select(endpoint, query, timeout):
    response = requests.post(
        endpoint, data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def term(binding):
    return {
        "type": binding["type"],
        "value": binding["value"],
        **({"datatype": binding["datatype"]} if "datatype" in binding else {}),
        **({"lang": binding["xml:lang"]} if "xml:lang" in binding else {}),
    }


def observations(endpoint, pattern, limit, timeout, named_graphs=False):
    # Explicit GRAPH queries inspect named-graph assertions; default queries
    # depend on repository dataset configuration and inference settings.
    triple = "GRAPH ?graph { " + pattern + " }" if named_graphs else pattern
    query = "SELECT * WHERE { " + triple + " } LIMIT " + str(limit)
    rows = select(endpoint, query, timeout)
    return [
        {key: term(value) for key, value in row.items()}
        for row in rows
    ]


def inspect(endpoint, timeout=20, limit=20, named_graphs=False):
    if not (1 <= limit <= 100):
        raise ValueError("limit must be between 1 and 100")
    results = []
    for family, identifiers in (("asset", ASSET_IDS), ("product", PRODUCT_IDS)):
        for identifier in identifiers:
            for key, predicate in PREDICATES.items():
                if not key.endswith("_" + family):
                    continue
                record = {
                    "family": family, "identifier": identifier,
                    "predicate": predicate, "scope": "named_graphs" if named_graphs else "default_dataset",
                    "interpretation": "matching_literal_only_not_verified_identity",
                }
                pattern = "?subject " + safe_iri(predicate) + " " + json.dumps(identifier) + " ."
                try:
                    record["matches"] = observations(endpoint, pattern, limit, timeout, named_graphs)
                    record["status"] = "ok"
                except (requests.RequestException, ValueError, KeyError) as exc:
                    record["status"], record["error"] = "error", str(exc)
                results.append(record)
    details = []
    for predicate in DETAIL_PREDICATES:
        record = {"predicate": predicate,
                  "scope": "named_graphs" if named_graphs else "default_dataset"}
        try:
            record["observations"] = observations(
                endpoint, "?subject " + safe_iri(predicate) + " ?object .",
                limit, timeout, named_graphs)
            record["status"] = "ok"
        except (requests.RequestException, ValueError, KeyError) as exc:
            record["status"], record["error"] = "error", str(exc)
        details.append(record)
    return {
        "method": "phase6e_resource_level_read_only_inspection",
        "endpoint": endpoint, "named_graphs": named_graphs,
        "identifier_resource_matches": results,
        "relationship_observations": details,
        "verified_cross_domain_identity": False,
        "verified_physical_membership": False,
        "limitations": [
            "Identifier matches are RDF literal equality, not identity assertions.",
            "Matching product candidates do not establish installed products.",
            "Sample limits truncate observations and cannot establish completeness.",
            "Default-dataset and named-graph scopes can differ with GraphDB configuration.",
            "Named-graph mode reports graph context but does not independently verify source provenance.",
            "Observed endpoint or technical-property triples do not prove cross-domain joins.",
            "No SPARQL updates, ontology changes, or compiler repairs are performed.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--named-graphs", action="store_true",
                        help="Inspect GRAPH ?graph assertions instead of the default dataset")
    parser.add_argument("--output", type=Path,
                        default=Path("reports/phase6_resource_evidence.json"))
    args = parser.parse_args()
    result = inspect(args.graphdb_url, args.timeout, args.limit, args.named_graphs)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    failures = sum(item["status"] != "ok" for item in
                   result["identifier_resource_matches"] + result["relationship_observations"])
    print("Report:", output)
    print("Identifier probes:", len(result["identifier_resource_matches"]))
    print("Relationship probes:", len(result["relationship_observations"]))
    print("Probe failures:", failures)
    print("Identity and physical membership verified: no (not asserted)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
