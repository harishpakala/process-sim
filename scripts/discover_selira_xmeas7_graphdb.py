#!/usr/bin/env python3
"""Discover candidate XMEAS7 engineering triples from a live GraphDB repository."""
import argparse
import json
import os
import sys

from process_sim.selira.graphdb_discovery import inspect_xmeas7


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default=os.getenv(
        "GRAPHDB_SPARQL_URL", "http://localhost:7200/repositories/AAS"))
    parser.add_argument("--output", help="Optional JSON output file")
    args = parser.parse_args()
    try:
        result = inspect_xmeas7(args.graphdb)
    except Exception as exc:
        print(json.dumps({"status": "DISCOVERY_FAILED", "authorization": False,
                          "error": str(exc)}), file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(rendered + "\n")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
