#!/usr/bin/env python3
"""Phase 7C: read-only FI106 ECAD endpoint-to-PLC connectivity evidence audit.

This is exploratory edge discovery, not a claim of connected wiring. The device
endpoint and PLC endpoint sets are separately grounded in explicit ECAD triples.
No lexical, identifier-equality, or cross-domain join is introduced.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]
ECAD = "https://example.org/ecad/"
DEFAULT_ASSET = "https://aas.example.com/FI106"

def safe_literal(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid asset identifier")
    return json.dumps(value, ensure_ascii=True)

def safe_graph(value):
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
        c in value for c in ("<", ">", "\\", '"', "{", "}", "|", "^", "\r", "\n", " ")
    ):
        raise ValueError("Invalid graph IRI")
    return "<" + value + ">"

def compile_probes(asset_identifier, graph=None, limit=200):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    asset = safe_literal(asset_identifier)
    scope = "GRAPH " + (safe_graph(graph) or "?graph")
    device_path = ("?device ecad:hasAssetIdentifier ?asset . "
                   "FILTER(isLiteral(?asset) && STR(?asset) = " + asset + ") "
                   "?device ecad:hasConnectionPoints ?device_collection . "
                   "?device_collection ecad:hasEndPoint ?device_endpoint .")
    plc_path = "?plc_collection ecad:hasPLCEndPoint ?plc_endpoint ."
    # Exact one-hop predicates are discovered rather than guessed. Both
    # directions and the intermediate resource's type are retained.
    patterns = {
        "device_endpoints": device_path,
        "device_endpoint_outgoing": device_path + " ?device_endpoint ?predicate ?neighbor .",
        "device_endpoint_incoming": device_path + " ?neighbor ?predicate ?device_endpoint .",
        "plc_endpoint_outgoing": plc_path + " ?plc_endpoint ?predicate ?neighbor .",
        "plc_endpoint_incoming": plc_path + " ?neighbor ?predicate ?plc_endpoint .",
        "direct_device_to_plc": device_path + " " + plc_path +
            " { { ?device_endpoint ?connecting_predicate ?plc_endpoint . } UNION "
            "{ ?plc_endpoint ?connecting_predicate ?device_endpoint . } }",
        "shared_intermediate": device_path + " " + plc_path +
            " ?device_endpoint ?device_edge ?intermediate . "
            "?plc_endpoint ?plc_edge ?intermediate . FILTER(isIRI(?intermediate))",
    }
    prefix = "PREFIX ecad: <" + ECAD + ">\n"
    return {name: prefix + "SELECT DISTINCT * WHERE { " + scope + " { " + pattern +
            " } } LIMIT " + str(limit) for name, pattern in patterns.items()}

def query(endpoint, sparql, timeout):
    response = requests.post(endpoint, data={"query": sparql},
                             headers={"Accept": "application/sparql-results+json"}, timeout=timeout)
    response.raise_for_status()
    return response.json()["results"]["bindings"]

def inspect(asset_identifier, endpoint, graph=None, limit=200, timeout=30):
    probes = compile_probes(asset_identifier, graph, limit)
    result = {
        "phase": "7C", "method": "ecad_endpoint_connectivity_evidence_read_only",
        "asset_identifier": asset_identifier, "endpoint": endpoint,
        "graph_scope": graph or "all_named_graphs", "per_probe_limit": limit,
        "status": "ok", "probes": {},
        "verified_device_to_plc_connection": False,
        "full_q2_supported": False, "verified_cross_domain_identity": False,
        "verified_physical_membership": False, "router_integrated": False,
        "limitations": [
            "Direct/shared-resource candidate edges require predicate-level engineering review.",
            "Shared intermediate resource is not automatically an electrical connection.",
            "A zero-row probe is not proof of absence; results may be limited or graph-scoped.",
            "PLC endpoint association is not inferred from matching labels, identifiers, or positions.",
            "DEXPI-to-ECAD identity is not established.",
            "No GraphDB writes or installation/BOM/containment inference.",
        ],
    }
    for name, sparql in probes.items():
        entry = {"sparql": sparql, "status": "ok", "bindings": []}
        try:
            entry["bindings"] = query(endpoint, sparql, timeout)
            entry["binding_count"] = len(entry["bindings"])
            entry["possibly_truncated"] = len(entry["bindings"]) >= limit
        except (requests.RequestException, KeyError, ValueError) as exc:
            entry.update(status="error", error=str(exc))
            result["status"] = "error"
        result["probes"][name] = entry
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asset-identifier", default=DEFAULT_ASSET)
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--graph", help="Optional named-graph IRI")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--output", type=Path, default=Path("reports/phase7c_ecad_connectivity_evidence.json"))
    args = ap.parse_args(argv)
    try:
        report = inspect(args.asset_identifier, args.graphdb_url, args.graph, args.limit, args.timeout)
    except ValueError as exc:
        print("Invalid argument:", exc)
        return 2
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Report:", path)
    for name, entry in report["probes"].items():
        print(name + ":", entry["status"], entry.get("binding_count", 0),
              "(possibly truncated)" if entry.get("possibly_truncated") else "")
    print("Device-to-PLC connection verified: no (candidate edges require review)")
    return 0 if report["status"] == "ok" else 2

if __name__ == "__main__":
    raise SystemExit(main())
