#!/usr/bin/env python3
"""Phase 7B: read-only ECAD device/connection-point/PLC-endpoint path evidence.

No DEXPI-to-ECAD joins. Explicit path rows are observations, not installation
or cross-domain identity assertions. Incomplete paths remain incomplete.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]
ECAD = "https://example.org/ecad/"
DEFAULT_ASSET = "https://aas.example.com/FI106"

def literal(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid asset identifier")
    return json.dumps(value, ensure_ascii=True)

def safe_iri(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
        char in value for char in ("<", ">", "\\", '"', "{", "}", "|", "^", "\r", "\n", " ")
    ):
        raise ValueError("Unsafe graph IRI")
    return "<" + value + ">"

def compile_probes(asset_identifier, graph=None, limit=100):
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be 1..500")
    target = literal(asset_identifier)
    graph_clause = "GRAPH " + safe_iri(graph) if graph else "GRAPH ?graph"
    prefix = "PREFIX ecad: <" + ECAD + ">\n"
    # Do not assume the type of the collection or invent a collection-membership predicate.
    # First expose all edges around observed connection-point collections.
    patterns = {
        "devices": "?device ecad:hasAssetIdentifier ?asset . FILTER(isLiteral(?asset) && STR(?asset) = " + target + ") OPTIONAL { ?device ecad:hasConnectionPoints ?collection . }",
        "collection_outgoing": "?device ecad:hasAssetIdentifier ?asset . FILTER(isLiteral(?asset) && STR(?asset) = " + target + ") ?device ecad:hasConnectionPoints ?collection . ?collection ?collection_predicate ?connection_point .",
        "collection_incoming": "?device ecad:hasAssetIdentifier ?asset . FILTER(isLiteral(?asset) && STR(?asset) = " + target + ") ?device ecad:hasConnectionPoints ?collection . ?connection_point ?connection_predicate ?collection .",
        "plc_endpoints": "?connection_point ecad:hasPLCEndPoint ?plc_endpoint .",
    }
    return {name: prefix + "SELECT DISTINCT * WHERE { " + graph_clause + " { " + pattern + " } } LIMIT " + str(limit)
            for name, pattern in patterns.items()}

def select(endpoint, sparql, timeout):
    response = requests.post(endpoint, data={"query": sparql},
                             headers={"Accept": "application/sparql-results+json"}, timeout=timeout)
    response.raise_for_status()
    return response.json()["results"]["bindings"]

def inspect(asset_identifier, endpoint, graph=None, limit=100, timeout=30):
    probes = compile_probes(asset_identifier, graph, limit)
    result = {
        "phase": "7B", "method": "ecad_explicit_path_discovery_read_only",
        "asset_identifier": asset_identifier, "endpoint": endpoint,
        "graph_scope": graph or "all_named_graphs", "per_probe_limit": limit,
        "status": "ok", "probes": {},
        "full_q2_supported": False, "verified_cross_domain_identity": False,
        "verified_physical_membership": False, "router_integrated": False,
        "limitations": [
            "Collection edges are exploratory: their predicates and node roles require verification.",
            "PLC endpoint edges are not assumed to belong to the target device without a complete explicit path.",
            "Identifier matching selects ECAD subjects only; it does not establish DEXPI-to-ECAD identity.",
            "Named graph context is not independent engineering provenance verification.",
            "Results can be truncated at the per-probe limit.",
            "No GraphDB updates, inferred containment, installation, or BOM membership.",
        ],
    }
    for name, query in probes.items():
        entry = {"sparql": query, "status": "ok", "bindings": []}
        try:
            entry["bindings"] = select(endpoint, query, timeout)
            entry["binding_count"] = len(entry["bindings"])
            entry["possibly_truncated"] = len(entry["bindings"]) >= limit
        except (requests.RequestException, ValueError, KeyError) as exc:
            entry.update(status="error", error=str(exc))
            result["status"] = "error"
        result["probes"][name] = entry
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asset-identifier", default=DEFAULT_ASSET)
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--graph", help="Optional explicit named graph IRI")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--output", type=Path, default=Path("reports/phase7b_ecad_path_evidence.json"))
    args = ap.parse_args(argv)
    try:
        report = inspect(args.asset_identifier, args.graphdb_url, args.graph, args.limit, args.timeout)
    except ValueError as exc:
        print("Invalid argument:", exc)
        return 2
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Report:", output)
    for name, entry in report["probes"].items():
        print(name + ":", entry["status"], entry.get("binding_count", 0))
    print("Full Q2 supported: no; requires explicit path and cross-domain validation")
    return 0 if report["status"] == "ok" else 2

if __name__ == "__main__":
    raise SystemExit(main())
