"""Run the deterministic four-domain query against GraphDB and check the baseline.

Usage:
  python -m semantic.dtwise_graphdb_integration --endpoint http://localhost:7200/repositories/REPO
Optional HTTP Basic authentication: GRAPHDB_USER and GRAPHDB_PASSWORD environment variables.
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from semantic.dtwise_cross_domain import compile_cross_domain
from semantic.dtwise_four_domain_baseline import BASELINE, validate_result

QUESTION = "Which EngineeringBOM items correspond to ECAD devices and DEXPI objects and AssetInventory assets?"
HERE = Path(__file__).resolve().parent
INDEX = HERE / "ontology" / "dtwise" / "dtwise-schema-index.json"
CATALOG = HERE / "ontology" / "dtwise" / "cross-domain-mappings.json"


def execute(endpoint, sparql, timeout=60, username=None, password=None):
    parts = urlsplit(endpoint)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("GraphDB endpoint must be an absolute HTTP(S) URL")
    request = Request(
        endpoint,
        data=sparql.encode("utf-8"),
        headers={"Content-Type": "application/sparql-query",
                 "Accept": "application/sparql-results+json"},
        method="POST",
    )
    if username is not None:
        credentials = base64.b64encode((username + ":" + (password or "")).encode()).decode()
        request.add_header("Authorization", "Basic " + credentials)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def run(endpoint, index_path=INDEX, catalog_path=CATALOG, baseline_path=BASELINE,
        timeout=60, username=None, password=None):
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    compiled = compile_cross_domain(QUESTION, index, catalog,
                                    allow_candidate=True, limit=1000)
    sparql = compiled["sparql"]
    document = execute(endpoint, sparql, timeout=timeout,
                       username=username, password=password)
    actual, failures = validate_result(document, baseline)
    return {"counts": actual, "passed": not failures, "failures": failures,
            "mapping_status": baseline["mapping_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True,
                        help="Full GraphDB repository SPARQL endpoint URL")
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        result = run(args.endpoint, args.index, args.catalog, args.baseline,
                     timeout=args.timeout, username=os.environ.get("GRAPHDB_USER"),
                     password=os.environ.get("GRAPHDB_PASSWORD"))
    except (OSError, ValueError, KeyError, HTTPError, URLError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
