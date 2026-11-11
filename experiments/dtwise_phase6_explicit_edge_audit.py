#!/usr/bin/env python3
"""Phase 6F: read-only explicit-edge audit of Phase 6E named-graph observations.

Inspect edges adjacent to *observed RDF resource IRIs*, never join two
resources because identifier literals match. Graph context is retained.
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


def safe_iri(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
        char in value for char in ("<", ">", "\\", "\"", "{", "}", "|", "^", "\r", "\n")
    ):
        raise ValueError("Unsafe resource IRI")
    return "<" + value + ">"


def query(endpoint, sparql, timeout):
    response = requests.post(endpoint, data={"query": sparql},
                             headers={"Accept": "application/sparql-results+json"},
                             timeout=timeout)
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def convert(row):
    return {key: {"type": val["type"], "value": val["value"],
                  **({"datatype": val["datatype"]} if "datatype" in val else {}),
                  **({"lang": val["xml:lang"]} if "xml:lang" in val else {})}
            for key, val in row.items()}


def neighbors(endpoint, resource, direction, limit, timeout):
    resource_iri = safe_iri(resource)
    if direction == "outgoing":
        pattern = resource_iri + " ?predicate ?object ."
    elif direction == "incoming":
        pattern = "?subject ?predicate " + resource_iri + " ."
    else:
        raise ValueError("direction must be incoming or outgoing")
    sparql = "SELECT * WHERE { GRAPH ?graph { " + pattern + " } } LIMIT " + str(limit)
    return [convert(row) for row in query(endpoint, sparql, timeout)]


def collect_seeds(phase6e, per_group):
    if not phase6e.get("named_graphs"):
        raise ValueError("Phase 6E report must use --named-graphs")
    groups = {}
    for record in phase6e.get("identifier_resource_matches", []):
        if record.get("status") != "ok":
            continue
        label = record["family"] + ":" + record["identifier"]
        groups.setdefault(label, [])
        groups[label].extend(
            match["subject"]["value"] for match in record.get("matches", [])
            if match.get("subject", {}).get("type") == "uri"
        )
    for record in phase6e.get("relationship_observations", []):
        if record.get("status") != "ok":
            continue
        label = "predicate:" + record["predicate"]
        groups.setdefault(label, [])
        for match in record.get("observations", []):
            for field in ("subject", "object"):
                if match.get(field, {}).get("type") == "uri":
                    groups[label].append(match[field]["value"])
    # Limit per group, not per entire report. Stable deduplication preserves
    # observable sampling order without equating resources from different graphs.
    return {group: list(dict.fromkeys(resources))[:per_group]
            for group, resources in groups.items()}


def inspect(endpoint, phase6e, per_group=5, limit=30, timeout=20):
    if not 1 <= per_group <= 50 or not 1 <= limit <= 100:
        raise ValueError("per-group and limit must be within supported bounds")
    seeds = collect_seeds(phase6e, per_group)
    results = []
    # A resource may occur in multiple groups; query it once, retain labels.
    resource_groups = {}
    for group, resources in seeds.items():
        for resource in resources:
            resource_groups.setdefault(resource, []).append(group)
    for resource, groups in resource_groups.items():
        record = {"resource": resource, "seed_groups": groups,
                  "outgoing": [], "incoming": [], "status": "ok"}
        for direction in ("outgoing", "incoming"):
            try:
                record[direction] = neighbors(endpoint, resource, direction, limit, timeout)
            except (requests.RequestException, ValueError, KeyError) as exc:
                record["status"] = "error"
                record.setdefault("errors", []).append(
                    {"direction": direction, "message": str(exc)})
        results.append(record)
    return {
        "method": "phase6f_explicit_edge_audit_read_only",
        "endpoint": endpoint,
        "seed_source": "phase6e_named_graphs",
        "per_group_limit": per_group,
        "per_direction_limit": limit,
        "seed_groups": {k: len(v) for k, v in seeds.items()},
        "resource_audits": results,
        "verified_cross_domain_identity": False,
        "verified_physical_membership": False,
        "limitations": [
            "Edges are observed graph statements, not automatically verified engineering semantics.",
            "No cross-domain resource equivalence is inferred from identifier equality.",
            "Named graph location is not independent source provenance verification.",
            "Outgoing and incoming observations are truncated at the configured limits.",
            "No automatic planner repairs, graph writes, or physical membership inference.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=Path("reports/phase6_resource_evidence_named_graphs.json"))
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--per-group", type=int, default=5)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--output", type=Path,
                        default=Path("reports/phase6_explicit_edge_audit.json"))
    args = parser.parse_args()
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    phase6e = json.loads(input_path.read_text(encoding="utf-8"))
    result = inspect(args.graphdb_url, phase6e, args.per_group, args.limit, args.timeout)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    errors = sum(r["status"] != "ok" for r in result["resource_audits"])
    print("Report:", output)
    print("Unique resources audited:", len(result["resource_audits"]))
    print("Resource audits with errors:", errors)
    print("Identity or physical membership verified: no")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
