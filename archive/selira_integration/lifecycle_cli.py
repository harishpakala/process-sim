"""Run SC-01 revision comparison without changing engineering named graphs.

Capture snapshots separately to avoid mutating production data. The comparison
uses a deterministic SC-01 reference evaluator; native SHACL and RDF history
are separate integration milestones.
"""

# Created: 2026-10-29
# Author: Harish
import argparse
import json
from .graphdb_snapshot import read_snapshot, save_snapshot, load_snapshot
from .lifecycle import Lifecycle

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--endpoint", required=True)
    capture.add_argument("--inventory-graph", required=True)
    capture.add_argument("--catalog-graph", required=True)
    capture.add_argument("--revision", required=True)
    capture.add_argument("--catalog-complete", action="store_true",
                         help="Only assert if independently verified")
    capture.add_argument("--output", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--history", required=True)
    args = parser.parse_args()
    if args.command == "capture":
        snapshot = read_snapshot(args.endpoint, args.inventory_graph,
            args.catalog_graph, args.revision, complete=args.catalog_complete)
        save_snapshot(snapshot, args.output)
        print(json.dumps({"revision": snapshot.revision,
            "assets": len(snapshot.assigned), "products": len(snapshot.catalog),
            "complete": snapshot.complete}))
    else:
        before, after = load_snapshot(args.before), load_snapshot(args.after)
        if before.revision == after.revision:
            raise ValueError("Distinct source revision identifiers required")
        lifecycle = Lifecycle(args.history)
        lifecycle.initialize(before)
        result = lifecycle.apply(before, after)
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["baseline_agreement"] or not result["unaffected_unchanged"]:
            raise SystemExit("Lifecycle correctness assertion failed")

if __name__ == "__main__":
    main()
