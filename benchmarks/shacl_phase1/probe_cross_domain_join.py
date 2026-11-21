"""Probe approved cross-domain identifier joins in AAST named instance graphs.

This is a data-compatibility diagnostic, not a full Phase-1 plan compiler.
No LLM calls; SELECT only. A zero-row join is not a semantic failure.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
from benchmarks.shacl_phase1.execute_single_domain_sparql import execute_query


def iri(value):
    if not isinstance(value, str) or not value.startswith(("http://", "https://")) or any(
            c in value for c in '<>\r\n\t '):
        raise ValueError("Invalid graph or predicate IRI")
    return "<" + value + ">"


def build_join_query(mapping, graphs, limit=20):
    """Build a graph-scoped identifier equality probe from an approved mapping."""
    if mapping.get("verified") is not True:
        raise ValueError("Mapping is not approved")
    left, right = mapping["left_domain"], mapping["right_domain"]
    if left == right or left not in graphs or right not in graphs:
        raise ValueError("Distinct mapped domains must have instance graphs")
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("LIMIT must be positive")
    return (
        "SELECT DISTINCT ?leftEntity ?rightEntity ?identifier WHERE {\n"
        f"  GRAPH {iri(graphs[left])} {{ ?leftEntity {iri(mapping['left_property'])} ?identifier . }}\n"
        f"  GRAPH {iri(graphs[right])} {{ ?rightEntity {iri(mapping['right_property'])} ?identifier . }}\n"
        f"}}\nLIMIT {limit}\n"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mapping-id", default="dexpi-ecad-asset-identifier")
    ap.add_argument("--mappings", type=Path,
                    default=ROOT / "semantic/ontology2/dtwise/cross-domain-mappings.json")
    ap.add_argument("--graphs", type=Path,
                    default=ROOT / "benchmarks/shacl_phase1/aast_instance_graphs.json")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAST")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--output", type=Path,
                    default=ROOT / "benchmark_results/cross_domain_join_probe.json")
    args = ap.parse_args(argv)
    if args.timeout <= 0:
        ap.error("--timeout must be positive")
    mappings = json.loads(args.mappings.read_text(encoding="utf-8"))
    selected = [m for m in mappings if m.get("id") == args.mapping_id]
    if len(selected) != 1:
        ap.error("Expected exactly one approved mapping with that ID")
    graphs = json.loads(args.graphs.read_text(encoding="utf-8"))
    try:
        sparql = build_join_query(selected[0], graphs, args.limit)
    except (ValueError, KeyError) as exc:
        ap.error(str(exc))
    print(sparql, flush=True)
    result = execute_query(args.endpoint, sparql, args.timeout)
    report = {"mapping_id": args.mapping_id, "sparql": sparql,
              "semantic_status": "not_checked", **result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"GraphDB: {result['status']} | ROWS: {result['row_count']}", flush=True)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    print("Saved:", args.output, flush=True)
    return 0 if result["status"] in ("executed_with_results", "executed_zero_rows") else 1


if __name__ == "__main__":
    sys.exit(main())
