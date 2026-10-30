#!/usr/bin/env python3
"""Expand discovered XMEAS7 subjects using live read-only GraphDB SPARQL."""
import argparse
import json
import sys

from process_sim.selira.graphdb_expansion import expand_discovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", default="selira-xmeas7-discovery.json")
    parser.add_argument("--output", default="selira-xmeas7-expanded.json")
    parser.add_argument("--graphdb", help="Override endpoint from discovery JSON")
    args = parser.parse_args()
    try:
        with open(args.discovery, encoding="utf-8") as stream:
            discovery = json.load(stream)
        result = expand_discovery(discovery, endpoint=args.graphdb)
        with open(args.output, "w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print("Wrote %s: %s triples; authorization=%s" % (
            args.output, len(result["facts"]), result["authorization"]))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "EXPANSION_FAILED",
                          "authorization": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
