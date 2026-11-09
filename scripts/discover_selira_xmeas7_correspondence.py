#!/usr/bin/env python3
"""Search GraphDB for candidate cross-domain engineering identifiers."""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
import sys

from process_sim.selira.graphdb_correspondence import search_correspondence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphdb", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--output", default="selira-xmeas7-correspondence.json")
    args = parser.parse_args()
    try:
        result = search_correspondence(args.graphdb)
        with open(args.output, "w", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
        print("Wrote %s: %d candidate triples; authorization=False" %
              (args.output, sum(result["counts"].values())))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "DISCOVERY_FAILED", "authorization": False,
                          "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
