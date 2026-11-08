#!/usr/bin/env python3
"""Read-only focused XMEAS7 engineering relationship discovery."""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
import sys

from process_sim.selira.graphdb_focused_relationships import focused_relationships


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correspondence", default="selira-xmeas7-correspondence.json")
    parser.add_argument("--output", default="selira-xmeas7-focused.json")
    parser.add_argument("--graphdb", help="Override the report's GraphDB endpoint")
    args = parser.parse_args()
    try:
        with open(args.correspondence, encoding="utf-8") as handle:
            report = json.load(handle)
        result = focused_relationships(report, endpoint=args.graphdb)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print("Wrote %s: %d triples; pages=%d; truncated=%s; authorization=False" %
              (args.output, len(result["facts"]), result["pagesFetched"],
               result["truncated"]))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FOCUSED_DISCOVERY_FAILED",
                          "authorization": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
