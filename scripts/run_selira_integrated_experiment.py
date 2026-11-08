#!/usr/bin/env python3
"""Run all five experimental SC checks and both README-proposed CAC checks.

Existing SC-02/03/04 prototype IDs are retained; see contractCatalog for
README numbering differences. Synthetic V does not certify engineering data.
"""

# Created: 2026-10-30
# Author: Harish
import argparse
import json
from pathlib import Path

from process_sim.selira.sc01_contract import evaluate_sc01
from process_sim.selira.sc01_graphdb_evidence import assess_graphdb_sc01
from process_sim.selira.sc02_contract import evaluate_sc02, assess_graphdb_sc02
from process_sim.selira.sc03_contract import evaluate_sc03, assess_graphdb_sc03
from process_sim.selira.sc04_contract import evaluate_sc04, assess_graphdb_sc04
from process_sim.selira.sc05_contract import evaluate_sc05, assess_graphdb_sc05
from process_sim.selira.cac_contracts import evaluate_cac, REQUIREMENTS
from process_sim.selira.integrated_contracts import aggregate
from run_selira_sc01_experiment import synthetic_case as sc01_fixture
from run_selira_sc02_experiment import synthetic_case as sc02_fixture
from run_selira_sc03_experiment import synthetic_case as sc03_fixture
from run_selira_sc04_experiment import synthetic_case as sc04_fixture

NODE = "nsu=urn:process-sim:opcua;s=TEP.Measurements.XMEAS7"


def sc05_fixture(contradiction=False):
    return {"target": {"signal": "XMEAS7", "nodeId": NODE, "revision": "SYNTHETIC-R1"},
            "bindingAssertions": [{
                "signal": "XMEAS7", "nodeId": NODE, "revision": "SYNTHETIC-R1",
                "verdict": "CONTRADICTED" if contradiction else "BOUND",
                "authority": "AUTHENTICATED", "evidenceRef": "synthetic://binding",
                "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"}}]}


def cac_fixture(contract, mode="V"):
    values = {
        "runId": "RUN-SYNTHETIC-1", "timeInterval": "SYNTHETIC-T0/T1",
        "units": "kPa", "provenance": "SYNTHETIC-PROVENANCE",
        "measurementCoverage": "COMPLETE",
        "approval": "SYNTHETIC-APPROVED",
        "targetProperty": "reactorPressure", "configuration": "SYNTHETIC-TEP-A"}
    requirements = {k: values[k] for k in REQUIREMENTS[contract]}
    checks = [{"requirement": k, "expected": v,
               "verdict": "VIOLATED" if mode == "F" and k == next(iter(requirements)) else "MET",
               "authority": "AUTHENTICATED",
               "evidenceRef": "synthetic://" + k,
               "provenance": {"source": "SYNTHETIC_TEST_FIXTURE"}}
              for k, v in requirements.items()]
    if mode == "U":
        checks = checks[:-1]
    return {"inScope": mode != "NA", "requirements": requirements, "checks": checks}


def run_scenario(mode, report=None):
    if report is None:
        contradiction = mode == "F"
        sc = [
            evaluate_sc01(sc01_fixture("CONTRADICTED" if contradiction else "VERIFIED")),
            evaluate_sc02(sc02_fixture("temperature" if contradiction else "pressure")),
            evaluate_sc03(sc03_fixture("degC" if contradiction else "kPa")),
            evaluate_sc04(sc04_fixture("INAPPLICABLE" if contradiction else "APPLICABLE")),
            evaluate_sc05(sc05_fixture(contradiction))]
    else:
        sc = [assess_graphdb_sc01(report), assess_graphdb_sc02(report),
              assess_graphdb_sc03(report), assess_graphdb_sc04(report),
              assess_graphdb_sc05(report)]
    source = ("F" if any(r["status"] == "F" for r in sc) else
              "V" if all(r["status"] == "V" for r in sc) else "U")
    cac_mode = mode if report is None else "U"
    cac = [evaluate_cac(name, cac_fixture(name, cac_mode) if report is None
                        else {"inScope": True, "requirements": {}, "checks": []},
                        source_status=source) for name in REQUIREMENTS]
    results = sc + cac
    return {"scenario": mode, "fixture": report is None,
            "contracts": results, "decision": aggregate(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focused", default="selira-xmeas7-focused.json")
    parser.add_argument("--output", default="selira-integrated-results.json")
    args = parser.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    scenarios = [run_scenario("synthetic-verified"), run_scenario("F"),
                 run_scenario("real-XMEAS7", report)]
    # Include independent CAC U/NA fixtures, without treating them as real evidence.
    controls = {name: {mode: evaluate_cac(name, cac_fixture(name, mode), "V")
                       for mode in ("V", "F", "U", "NA")}
                for name in REQUIREMENTS}
    payload = {
        "experiment": "SELiRA integrated SC/CAC prototype",
        "contractCatalog": {
            "prototype": {"SC-02": "quantity-kind", "SC-03": "measurement-unit",
                          "SC-04": "revision applicability", "SC-05": "operational binding"},
            "readmeProposal": {"SC-02": "engineering-to-signal meaning consistency",
                               "SC-03": "configuration and revision applicability",
                               "CAC-01": "operational evidence fitness",
                               "CAC-02": "engineering restriction fitness"},
            "warning": "Prototype SC numbering is not reconciled with README proposal"},
        "scenarios": scenarios, "cacControls": controls,
        "limitations": ["Synthetic assertions are not independently authenticated",
                        "No live OPC UA or TimescaleDB measurements verified",
                        "Real CAC tasks and approved restrictions not supplied",
                        "No engineering certification or authorization issued"]}
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    for scenario in scenarios:
        print(scenario["scenario"] + ": " +
              " ".join(r["contract"] + "=" + r["status"] for r in scenario["contracts"]) +
              " source=" + scenario["decision"]["sourceQualification"] +
              " authorization=False")
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
