#!/usr/bin/env python3
"""Run SC-01 synthetic V/F controls and a real-evidence U case."""
import argparse
import json
from pathlib import Path

from process_sim.selira.sc01_contract import evaluate_sc01, ROLES, LINKS
from process_sim.selira.sc01_graphdb_evidence import assess_graphdb_sc01


def synthetic_case(verdict="VERIFIED"):
    ids = {"DEXPI": "PI_101", "ECAD": "PI-1101", "PLC": "I10.19",
           "OPCUA": "nsu=urn:process-sim:opcua;s=TEP.Measurements.XMEAS7",
           "TEP": "XMEAS7"}
    assertions = []
    for source, target in LINKS:
        assertions.append({
            "fromRole": source, "toRole": target,
            "fromId": ids[source], "toId": ids[target],
            "verdict": "CONTRADICTED" if verdict == "CONTRADICTED"
                       and source == "DEXPI" else "VERIFIED",
            "revision": "SYNTHETIC-R1",
            "authority": "AUTHENTICATED",
            "evidenceRef": "synthetic://" + source + "-" + target,
            "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"},
        })
    return {"caseId": "SC01-T2" if verdict == "CONTRADICTED" else "SC01-T1",
            "revision": "SYNTHETIC-R1", "entities": ids,
            "assertions": assertions, "fixture": True}


def graphdb_case(report):
    if report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB discovery report")
    # GraphDB facts are discovery observations, not authenticated correspondence
    # assertions. Never upgrade string matches or provisional mappings to V.
    return {
        "caseId": "SC01-T3",
        "revision": "UNESTABLISHED",
        "entities": {"DEXPI": "PI_101", "ECAD": "PI-1101",
                     "PLC": "I10.19",
                     "OPCUA": "nsu=urn:process-sim:opcua;s=TEP.Measurements.XMEAS7",
                     "TEP": "XMEAS7"},
        "assertions": [],
        "sourceStatus": report["status"],
        "observedFacts": len(report.get("facts", [])),
        "truncated": report.get("truncated", True),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-sc01-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    cases = [synthetic_case(), synthetic_case("CONTRADICTED")]
    results = []
    for case in cases:
        outcome = evaluate_sc01(case)
        outcome["fixture"] = bool(case.get("fixture"))
        results.append(outcome)
    observed = assess_graphdb_sc01(report)
    observed["fixture"] = False
    results.append(observed)
    output = {"experiment": "SC-01", "results": results,
              "warning": "Synthetic controls do not certify GraphDB engineering evidence."}
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    for r in results:
        print("%s: %s (fixture=%s; authorization=False)" %
              (r["caseId"], r["status"], r["fixture"]))
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
