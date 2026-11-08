#!/usr/bin/env python3
"""Run SC-04 synthetic applicability controls and real GraphDB discovery."""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
from pathlib import Path

from process_sim.selira.sc04_contract import evaluate_sc04, assess_graphdb_sc04


def synthetic_case(verdict="APPLICABLE"):
    return {"caseId": "SC04-T1" if verdict == "APPLICABLE" else "SC04-T2",
            "fixture": True,
            "task": {"configuration": "SYNTHETIC-TEP-A", "revision": "SYNTHETIC-R1"},
            "applicabilityAssertions": [{
                "configuration": "SYNTHETIC-TEP-A",
                "revision": "SYNTHETIC-R1",
                "verdict": verdict,
                "authority": "AUTHENTICATED",
                "evidenceRef": "synthetic://configuration-revision-applicability",
                "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"},
            }]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-sc04-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    results = []
    for case in (synthetic_case(), synthetic_case("INAPPLICABLE")):
        outcome = evaluate_sc04(case)
        outcome["fixture"] = True
        results.append(outcome)
    observed = assess_graphdb_sc04(report)
    observed["fixture"] = False
    results.append(observed)
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump({"experiment": "SC-04", "results": results,
                   "warning": "Synthetic assertions do not certify real engineering evidence."},
                  handle, indent=2)
        handle.write("\n")
    for result in results:
        print("%s: %s (fixture=%s; authorization=False)" %
              (result["caseId"], result["status"], result["fixture"]))
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
