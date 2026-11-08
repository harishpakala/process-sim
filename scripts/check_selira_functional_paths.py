"""Smoke-test SELiRA functional correspondence against a running GraphDB repository.

Run from the repository root:
    python scripts/check_selira_functional_paths.py

Override the default endpoint with GRAPHDB_SPARQL_ENDPOINT if needed.
This checks structural evidence only; it does not verify live OPC UA bindings,
physical installation, or consumer authorization.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

import os
import sys

from process_sim.selira.functional_paths import resolve_functional_paths

FUNCTION_IDS = ("PI_101", "PI_102", "PI_103")
DEFAULT_ENDPOINT = "http://localhost:7200/repositories/AAS"


def main() -> int:
    endpoint = os.environ.get("GRAPHDB_SPARQL_ENDPOINT", DEFAULT_ENDPOINT)
    print(f"GraphDB endpoint: {endpoint}")
    try:
        results = resolve_functional_paths(FUNCTION_IDS, endpoint=endpoint)
    except Exception as exc:
        print(f"GraphDB functional-path query failed: {exc}", file=sys.stderr)
        return 2

    unexpected = False
    for instrument in FUNCTION_IDS:
        result = results[instrument]
        print(f"\n{instrument}: {result['status']}")
        for path in result["paths"]:
            print(f"  Signal: {path['signal']}")
            print(f"  PLC: {path['plcAddress']}")
            print(f"  ECAD: {path['ecadId']}")
        print(f"  Operational binding: {result['operational_binding']}")
        print(f"  Consumer authorized: {result['consumer_authorized']}")

        if (
            result["status"] != "structurally_supported_provisional"
            or result["operational_binding"] != "unverified"
            or result["consumer_authorized"] is not False
        ):
            unexpected = True

    if unexpected:
        print("\nFAIL: At least one path differs from the expected provisional, fail-closed state.")
        return 1

    print("\nPASS: Three structurally supported provisional paths; no live binding or authorization asserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
