#!/usr/bin/env python3
"""Run SC-03 synthetic compatibility controls and real GraphDB evidence."""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
from pathlib import Path
from process_sim.selira.sc03_contract import evaluate_sc03, assess_graphdb_sc03


def synthetic_case(operational="kPa"):
    return {"caseId": "SC03-T1" if operational == "kPa" else "SC03-T2",
            "revision": "SYNTHETIC-R1", "fixture": True,
            "unitAssertions": [
                {"side": side, "unit": unit, "revision": "SYNTHETIC-R1",
                 "authority": "AUTHENTICATED",
                 "evidenceRef": "synthetic://" + side + "-unit",
                 "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"}}
                for side, unit in (("engineering", "bar"),
                                   ("operational", operational))]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-sc03-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    results = []
    for case in (synthetic_case(), synthetic_case("degC")):
        result = evaluate_sc03(case)
        result["fixture"] = True
        results.append(result)
    real = assess_graphdb_sc03(report)
    real["fixture"] = False
    results.append(real)
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump({"experiment": "SC-03", "results": results,
                   "warning": "Synthetic assertions do not certify GraphDB evidence."},
                  handle, indent=2)
        handle.write("\n")
    for result in results:
        print("%s: %s (fixture=%s; authorization=False)" %
              (result["caseId"], result["status"], result["fixture"]))
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
