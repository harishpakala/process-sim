#!/usr/bin/env python3
"""Execute SC-02 V/F synthetic controls and GraphDB unknown case."""
import argparse
import json
from pathlib import Path

from process_sim.selira.sc02_contract import evaluate_sc02, assess_graphdb_sc02


def synthetic_case(operational="pressure"):
    case_id = "SC02-T1" if operational == "pressure" else "SC02-T2"
    return {"caseId": case_id, "revision": "SYNTHETIC-R1",
            "fixture": True,
            "quantityAssertions": [
                {"side": side, "quantityKind": kind, "revision": "SYNTHETIC-R1",
                 "authority": "AUTHENTICATED",
                 "evidenceRef": "synthetic://" + side + "-quantity",
                 "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"}}
                for side, kind in (("engineering", "pressure"),
                                   ("operational", operational))]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-sc02-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    results = []
    for case in (synthetic_case(), synthetic_case("temperature")):
        result = evaluate_sc02(case)
        result["fixture"] = True
        results.append(result)
    real = assess_graphdb_sc02(report)
    real["fixture"] = False
    results.append(real)
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump({"experiment": "SC-02", "results": results,
                   "warning": "Synthetic assertions do not certify GraphDB evidence."},
                  handle, indent=2)
        handle.write("\n")
    for result in results:
        print("%s: %s (fixture=%s; authorization=False)" %
              (result["caseId"], result["status"], result["fixture"]))
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
