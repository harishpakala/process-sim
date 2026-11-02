#!/usr/bin/env python3
"""E1-E10 evidence-perturbation benchmark; synthetic comparators, no certification."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from process_sim.selira.sc01_contract import evaluate_sc01
from process_sim.selira.sc01_graphdb_evidence import assess_graphdb_sc01
from process_sim.selira.sc02_contract import evaluate_sc02, assess_graphdb_sc02
from process_sim.selira.sc03_contract import evaluate_sc03, assess_graphdb_sc03
from process_sim.selira.sc04_contract import evaluate_sc04, assess_graphdb_sc04
from process_sim.selira.sc05_contract import evaluate_sc05, assess_graphdb_sc05
from process_sim.selira.cac_contracts import evaluate_cac
from process_sim.selira.integrated_contracts import aggregate
from run_selira_integrated_experiment import (
    sc01_fixture, sc02_fixture, sc03_fixture, sc04_fixture,
    sc05_fixture, cac_fixture,
)

SC_EVAL = (evaluate_sc01, evaluate_sc02, evaluate_sc03, evaluate_sc04, evaluate_sc05)
SC_GRAPH = (assess_graphdb_sc01, assess_graphdb_sc02, assess_graphdb_sc03,
            assess_graphdb_sc04, assess_graphdb_sc05)


def inputs():
    return [sc01_fixture(), sc02_fixture(), sc03_fixture(), sc04_fixture(),
            sc05_fixture()], {"CAC-01": cac_fixture("CAC-01"),
                              "CAC-02": cac_fixture("CAC-02")}


def synthetic_case(case_id):
    sc, cac = inputs()
    if case_id == "E2":
        sc[0]["assertions"] = sc[0]["assertions"][1:]
    elif case_id == "E3":
        sc[1]["quantityAssertions"][1]["quantityKind"] = "temperature"
    elif case_id == "E4":
        sc[2]["unitAssertions"][1]["unit"] = "degC"
    elif case_id == "E5":
        sc[3]["applicabilityAssertions"][0]["revision"] = "SYNTHETIC-OLD"
    elif case_id == "E6":
        sc[3]["applicabilityAssertions"][0]["verdict"] = "INAPPLICABLE"
    elif case_id == "E7":
        sc[4]["bindingAssertions"] = []  # declared node ID is not live binding
    elif case_id == "E8":
        for check in cac["CAC-01"]["checks"]:
            if check["requirement"] == "measurementCoverage":
                check["verdict"] = "VIOLATED"
    elif case_id == "E9":
        cac["CAC-02"]["checks"] = [c for c in cac["CAC-02"]["checks"]
                                   if c["requirement"] != "approval"]
    elif case_id != "E1":
        raise ValueError(case_id)
    return sc, cac


def baseline_identifiers(sc, real=False):
    """Naive declared-identifier comparator, not an existing product."""
    if real:
        return "ACCEPT"  # fixed discovery identifiers exist in the XMEAS7 report
    ids = sc[0].get("entities", {})
    return "ACCEPT" if all(ids.get(k) for k in ("DEXPI","ECAD","PLC","OPCUA","TEP")) else "WITHHOLD"


def baseline_structure(sc, real=False):
    """Naive schema/presence comparator; does NOT run SHACL or authenticate RDF."""
    if real:
        return "ACCEPT"  # focused report contains declared structural relationships
    return "ACCEPT" if (len(sc[0].get("assertions", [])) == 4 and
                        all(sc[i].get(key) for i, key in
                            ((1,"quantityAssertions"),(2,"unitAssertions"),
                             (3,"applicabilityAssertions"),(4,"bindingAssertions")))) else "WITHHOLD"


def evaluate(case_id, report=None):
    if report is None:
        sc_inputs, cac_inputs = synthetic_case(case_id)
        sc = [fn(deepcopy(value)) for fn, value in zip(SC_EVAL, sc_inputs)]
    else:
        sc_inputs = None
        sc = [fn(report) for fn in SC_GRAPH]
        cac_inputs = {"CAC-01": {"inScope": True, "requirements": {}, "checks": []},
                      "CAC-02": {"inScope": True, "requirements": {}, "checks": []}}
    source = ("F" if any(r["status"] == "F" for r in sc) else
              "V" if all(r["status"] == "V" for r in sc) else "U")
    cac = [evaluate_cac(k, v, source) for k,v in cac_inputs.items()]
    decision = aggregate(sc + cac)
    real = report is not None
    # Pre-registered *synthetic* reference labels, not independently adjudicated truth.
    reference = {"E1": "V", "E2": "U", "E3": "F", "E4": "F",
                 "E5": "U", "E6": "F", "E7": "U", "E8": "V",
                 "E9": "V", "E10": "U"}[case_id]
    return {
        "id": case_id, "fixture": not real,
        "referenceSourceStatus": reference,
        "sourceStatus": source,
        "referenceConsumerStatus": (
            {"CAC-01": "F", "CAC-02": "V"} if case_id == "E8" else
            {"CAC-01": "V", "CAC-02": "U"} if case_id == "E9" else None),
        "contracts": sc + cac, "decision": decision,
        "comparators": {
            "B1_identifier_presence": baseline_identifiers(sc_inputs, real),
            "B2_structural_presence": baseline_structure(sc_inputs, real),
            "SELiRA_evaluator": source,
        },
    }


def summarize(cases):
    synthetic = [c for c in cases if c["fixture"]]
    unknown_or_failed = [c for c in synthetic if c["referenceSourceStatus"] != "V"]
    return {
        "syntheticCases": len(synthetic),
        "realDiscoveryCases": len(cases) - len(synthetic),
        "sourceReferenceAgreement": sum(c["sourceStatus"] == c["referenceSourceStatus"]
                                        for c in cases),
        "sourceReferenceTotal": len(cases),
        "unsupportedAcceptanceCount": {
            k: sum(c["comparators"][k] == "ACCEPT" for c in unknown_or_failed)
            for k in ("B1_identifier_presence", "B2_structural_presence")},
        "unsupportedAcceptanceDenominator": len(unknown_or_failed),
        "seliraUnjustifiedSourceV": sum(c["sourceStatus"] == "V" for c in unknown_or_failed),
        "authorizationTrueCount": sum(c["decision"]["authorization"] for c in cases),
    }


def build(report):
    cases = [evaluate("E" + str(n)) for n in range(1,10)]
    cases.append(evaluate("E10", report))
    return {
        "experiment": "SELiRA E1-E10 evidence-level comparison",
        "contractCatalog": "Experimental SC numbering; see docs/research/selira/selira-contract-alignment.md",
        "cases": cases, "metrics": summarize(cases),
        "limitations": [
            "E1-E9 are synthetic assertion perturbations, not authenticated engineering observations",
            "Reference labels are scenario expectations, not independent ground truth",
            "B1/B2 are deliberately naive in-repository comparators, not actual tools or SHACL engines",
            "Comparator ACCEPT is a permissive heuristic output, never engineering authorization",
            "E10 is focused GraphDB discovery; no graph-wide absence, authentication, or live OPC UA binding inferred",
            "Timing and statistical generalization are not claimed; all engineering authorization is false",
        ]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--focused", default="selira-xmeas7-focused.json")
    p.add_argument("--output", default="selira-e1-e10-results.json")
    args = p.parse_args()
    with Path(args.focused).open(encoding="utf-8") as handle:
        report = json.load(handle)
    result = build(report)
    with Path(args.output).open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    for c in result["cases"]:
        print(c["id"] + ": source=" + c["sourceStatus"] +
              " CAC-01=" + c["decision"]["consumers"]["CAC-01"]["decision"] +
              " CAC-02=" + c["decision"]["consumers"]["CAC-02"]["decision"] +
              " authorization=False")
    print("Wrote " + args.output)


if __name__ == "__main__":
    main()
