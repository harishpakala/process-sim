#!/usr/bin/env python3
"""Mixed-verdict and task-specific consumer evidence experiment.

This supplements, not renumbers, the integrated SC/CAC prototype. All
assertions here are synthetic; no engineering approval is issued.
"""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_selira_integrated_experiment import run_scenario, cac_fixture
from process_sim.selira.cac_contracts import evaluate_cac
from process_sim.selira.integrated_contracts import SC_IDS, CAC_IDS, aggregate, conjunction


def mixed_case(name, overrides, cac_overrides=None):
    baseline = run_scenario("synthetic-verified")
    results = baseline["contracts"]
    for r in results:
        r["status"] = overrides.get(r["contract"], r["status"])
        r["fixture"] = True
        r["scenarioAssertion"] = "SYNTHETIC_STATUS_OVERRIDE_FOR_AGGREGATION_ONLY"
    for r in results:
        if r["contract"] in CAC_IDS:
            r["status"] = (cac_overrides or {}).get(r["contract"], r["status"])
    source = conjunction(r["status"] for r in results if r["contract"] in SC_IDS)
    for r in results:
        if r["contract"] in CAC_IDS:
            r["sourceQualification"] = source
            if source != "V" and "Source engineering qualification not verified" not in r["reasons"]:
                r["reasons"].append("Source engineering qualification not verified")
    decision = aggregate(results)
    return {"scenario": name, "fixture": True,
            "contracts": results, "decision": decision,
            "warning": "Status overrides test aggregation only, not evidence evaluation"}


def task_specific_controls():
    controls = {}
    for contract in CAC_IDS:
        case = cac_fixture(contract)
        # Demonstrate task-specific rejection independently of source status.
        checks = case["checks"]
        rejected = dict(case)
        rejected["checks"] = [dict(c) for c in checks]
        rejected["checks"][0]["verdict"] = "VIOLATED"
        incomplete = dict(case)
        incomplete["checks"] = checks[:-1]
        controls[contract] = {
            "verifiedTaskFixture": evaluate_cac(contract, case, "V"),
            "violatedTaskFixture": evaluate_cac(contract, rejected, "V"),
            "incompleteTaskFixture": evaluate_cac(contract, incomplete, "V"),
            "verifiedFitnessUnknownSource": evaluate_cac(contract, case, "U"),
            "outsideScope": evaluate_cac(contract, {"inScope": False}, "V"),
        }
    return controls


def build_report():
    mixed = [
        mixed_case("one-unknown", {"SC-03": "U"}),
        mixed_case("one-failure-and-one-unknown", {"SC-03": "F", "SC-04": "U"}),
        mixed_case("consumer-violation-source-verified", {}, {"CAC-01": "F"}),
        mixed_case("consumer-not-applicable-source-verified", {}, {"CAC-02": "NA"}),
        mixed_case("source-unknown-consumer-fitness-verified", {"SC-05": "U"}),
    ]
    return {"experiment": "SELiRA mixed SC/CAC aggregation",
            "fixture": True, "scenarios": mixed,
            "taskSpecificControls": task_specific_controls(),
            "contractIdentity": {
                "experimentalSC": {
                    "SC-01": "identity correspondence",
                    "SC-02": "quantity-kind compatibility",
                    "SC-03": "measurement-unit compatibility",
                    "SC-04": "configuration and revision applicability",
                    "SC-05": "operational binding"},
                "readmeProposals": {
                    "SC-02": "engineering-to-signal meaning consistency",
                    "SC-03": "configuration and revision applicability",
                    "CAC-01": "operational evidence fitness",
                    "CAC-02": "engineering restriction fitness"},
                "alignment": "UNRESOLVED",
                "policy": "Do not treat experimental SC-02/SC-03 numbering as README specifications"},
            "limitations": [
                "Mixed SC statuses are injected to test aggregation, not obtained by reevaluating engineering evidence",
                "Task-specific CAC fixtures are synthetic, not live historian data or approved restrictions",
                "No independent authentication, engineering certification, or authorization"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="selira-mixed-results.json")
    args = p.parse_args()
    payload = build_report()
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    for case in payload["scenarios"]:
        decisions = case["decision"]
        print(case["scenario"] + ": source=" + decisions["sourceQualification"] +
              " CAC-01=" + decisions["consumers"]["CAC-01"]["decision"] +
              " CAC-02=" + decisions["consumers"]["CAC-02"]["decision"] +
              " authorization=False")
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
