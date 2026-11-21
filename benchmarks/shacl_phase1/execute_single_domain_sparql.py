"""Execute saved compiled SELECT queries against a read-only SPARQL endpoint.

No planner calls, no GraphDB updates, and no claims of semantic correctness.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def execute_query(endpoint, sparql, timeout=60, default_graph_uri=None):
    """POST a read-only SELECT query and count SPARQL JSON bindings."""
    if not isinstance(sparql, str) or not sparql.lstrip().upper().startswith("SELECT"):
        return {"status": "unsupported_query", "row_count": None,
                "error": "Only SELECT queries are supported"}
    parameters = {"query": sparql}
    if default_graph_uri is not None:
        parameters["default-graph-uri"] = default_graph_uri
    data = urlencode(parameters).encode("utf-8")
    request = Request(endpoint, data=data, method="POST", headers={
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        bindings = payload["results"]["bindings"]
        if not isinstance(bindings, list):
            raise ValueError("SPARQL results.bindings must be an array")
        return {"status": "executed_with_results" if bindings else "executed_zero_rows",
                "row_count": len(bindings), "error": None}
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError,
            OSError, json.JSONDecodeError) as exc:
        return {"status": "execution_failed", "row_count": None,
                "error": f"{type(exc).__name__}: {exc}"}


def execute_results(items, endpoint, timeout=60, graph_mapping=None, compare=False):
    if not isinstance(items, list):
        raise ValueError("Expected JSON list of compilation results")
    seen = set()
    results = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Every result needs a string ID")
        if item["id"] in seen:
            raise ValueError("Duplicate result ID: " + item["id"])
        seen.add(item["id"])
        base = {"id": item["id"], "scenario_id": item.get("scenario_id"),
                "domain": item.get("domain"),
                "compilation_status": item.get("status"),
                "semantic_status": "not_checked"}
        domain = item.get("domain")
        graph_uri = graph_mapping.get(domain) if graph_mapping is not None else None
        base["graph_uri"] = graph_uri
        base["dataset_mode"] = "named_graph" if graph_mapping is not None else "repository_default"
        if graph_mapping is not None and graph_uri is None:
            result = {"status": "graph_mapping_missing", "row_count": None,
                      "error": "No instance graph configured for domain: " + str(domain)}
        elif item.get("status") != "compiled":
            result = {"status": "not_compiled", "row_count": None,
                      "error": item.get("error")}
        else:
            result = execute_query(endpoint, item.get("sparql"), timeout,
                                   default_graph_uri=graph_uri)
        if compare and item.get("status") == "compiled":
            baseline = execute_query(endpoint, item.get("sparql"), timeout)
            base["repository_default_status"] = baseline["status"]
            base["repository_default_row_count"] = baseline["row_count"]
            base["repository_default_error"] = baseline["error"]
            base["row_count_delta"] = (result["row_count"] - baseline["row_count"]
                                       if result["row_count"] is not None and
                                       baseline["row_count"] is not None else None)
        results.append({**base, **result})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAST")
    ap.add_argument("--input", type=Path, default=ROOT /
                    "benchmark_results/single_domain_sparql_results.json")
    ap.add_argument("--output", type=Path, default=ROOT /
                    "benchmark_results/single_domain_sparql_execution.json")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--graph-mapping", type=Path,
                    help="JSON domain-to-instance-graph URI mapping; omitted means repository default")
    ap.add_argument("--compare-default", action="store_true",
                    help="Also run against repository default dataset and report row-count differences")
    args = ap.parse_args(argv)
    if args.compare_default and not args.graph_mapping:
        ap.error("--compare-default requires --graph-mapping")
    parsed = urlsplit(args.endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        ap.error("--endpoint must be an HTTP(S) URL")
    if args.timeout <= 0:
        ap.error("--timeout must be positive")
    items = json.loads(args.input.read_text(encoding="utf-8"))
    graph_mapping = None
    if args.graph_mapping:
        graph_mapping = json.loads(args.graph_mapping.read_text(encoding="utf-8"))
        if not isinstance(graph_mapping, dict) or not graph_mapping or any(
                not isinstance(k, str) or not isinstance(v, str) or
                urlsplit(v).scheme not in ("http", "https") or not urlsplit(v).netloc
                for k, v in graph_mapping.items()):
            ap.error("--graph-mapping must be a nonempty JSON object of domain to HTTP(S) graph URI")
    results = execute_results(items, args.endpoint, args.timeout,
                              graph_mapping=graph_mapping, compare=args.compare_default)
    for result in results:
        print(f"{result['id']:<12} {result['status']:<24} rows={result['row_count']}",
              flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    counts = Counter(r["status"] for r in results)
    print("Summary:", dict(sorted(counts.items())))
    if args.compare_default:
        changed = sum(r.get("row_count_delta") not in (None, 0) for r in results)
        print("Queries with changed row counts:", changed)
    print("Semantic correctness: not checked")
    print("Output:", args.output)
    return 0 if results and all(r["status"] in (
        "executed_with_results", "executed_zero_rows") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
