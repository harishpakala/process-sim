#!/usr/bin/env python3
"""Inspect engineering relationships from a cross-domain discovery report."""
import argparse
import json
import sys

from process_sim.selira.graphdb_relationships import traverse_correspondence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correspondence", default="selira-xmeas7-correspondence.json")
    parser.add_argument("--output", default="selira-xmeas7-relationships.json")
    parser.add_argument("--graphdb", help="Override GraphDB SPARQL endpoint")
    args = parser.parse_args()
    try:
        with open(args.correspondence, encoding="utf-8") as handle:
            report = json.load(handle)
        result = traverse_correspondence(report, endpoint=args.graphdb)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print("Wrote %s: %d RDF triples; truncated=%s; authorization=False" %
              (args.output, len(result["facts"]), result["truncated"]))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "RELATIONSHIP_DISCOVERY_FAILED",
                          "authorization": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
