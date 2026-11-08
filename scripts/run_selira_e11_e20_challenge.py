#!/usr/bin/env python3
"""Exploratory E11-E20 challenge runner; preserve unsupported semantics."""

# Created: 2026-10-30
# Author: Harish
import argparse
from copy import deepcopy
import json
from pathlib import Path

from run_selira_e1_e10_benchmark import inputs, SC_EVAL
from process_sim.selira.cac_contracts import evaluate_cac
from process_sim.selira.integrated_contracts import aggregate

CHALLENGES = {
    "E11": ("Conflicting identity assertions", "supported-input perturbation"),
    "E12": ("Missing source provenance", "supported-input perturbation"),
    "E13": ("Mixed revision evidence", "supported-input perturbation"),
    "E14": ("Partially verified identity chain", "supported-input perturbation"),
    "E15": ("Pressure units with different scales", "supported-input perturbation"),
    "E16": ("Contradictory operational binding", "supported-input perturbation"),
    "E17": ("Missing operational consumer evidence", "supported-input perturbation"),
    "E18": ("Contradictory approval check", "supported-input perturbation"),
    "E19": ("Conflicting measurement time intervals", "schema extension needed"),
    "E20": ("Conflicting evidence authority levels", "schema extension needed"),
}


def scenario(case_id):
    if case_id not in CHALLENGES:
        raise ValueError(case_id)
    sc, cac = inputs()
    supported = True
    if case_id == "E11":
        conflict = deepcopy(sc[0]["assertions"][0])
        conflict["verdict"] = "CONTRADICTED"
        sc[0]["assertions"].append(conflict)
    elif case_id == "E12":
        sc[0]["assertions"][0].pop("provenance", None)
    elif case_id == "E13":
        conflict = deepcopy(sc[3]["applicabilityAssertions"][0])
        conflict["revision"] = "SYNTHETIC-OLD"
        sc[3]["applicabilityAssertions"].append(conflict)
    elif case_id == "E14":
        sc[0]["assertions"] = sc[0]["assertions"][:2]
    elif case_id == "E15":
        sc[2]["unitAssertions"][1]["unit"] = "bar"
    elif case_id == "E16":
        sc[4]["bindingAssertions"][0]["verdict"] = "CONTRADICTED"
    elif case_id == "E17":
        cac["CAC-01"]["checks"] = [
            c for c in cac["CAC-01"]["checks"]
            if c["requirement"] != "measurementCoverage"]
    elif case_id == "E18":
        for check in cac["CAC-02"]["checks"]:
            if check["requirement"] == "approval":
                check["verdict"] = "VIOLATED"
    elif case_id in ("E19", "E20"):
        supported = False
    return sc, cac, supported


def evaluate_challenge(case_id):
    sc, cac, supported = scenario(case_id)
    name, category = CHALLENGES[case_id]
    if not supported:
        return {
            "id": case_id, "challenge": name, "category": category,
            "evaluation": "NOT_RUN_UNSUPPORTED_SCHEMA",
            "reason": ("Cross-record temporal alignment" if case_id == "E19"
                       else "Conflict resolution using evidence authority")
                      + " is not represented by the existing fixture schema",
            "engineeringAuthorization": False,
        }
    results = [fn(deepcopy(value)) for fn, value in zip(SC_EVAL, sc)]
    source = ("F" if any(r["status"] == "F" for r in results)
              else "V" if all(r["status"] == "V" for r in results) else "U")
    consumers = [evaluate_cac(name, deepcopy(value), source)
                 for name, value in cac.items()]
    decision = aggregate(results + consumers)
    return {
        "id": case_id, "challenge": name, "category": category,
        "evaluation": "EXECUTED_EXPLORATORY",
        "inputEvidence": {"source": sc, "consumer": cac},
        "sourceContracts": [{"contract": r["contract"], "status": r["status"]}
                            for r in results],
        "sourceStatus": source,
        "consumerStatus": {
            r["contract"]: r["status"] for r in consumers
        },
        "decision": decision,
        "engineeringAuthorization": False,
        "referenceLabels": None,
        "warning": "No independent or pre-registered expected verdict",
    }


def build():
    cases = [evaluate_challenge(key) for key in CHALLENGES]
    return {
        "experiment": "SELiRA E11-E20 exploratory challenge set",
        "design": "Development scenarios, not independent holdout",
        "cases": cases,
        "summary": {
            "executed": sum(c["evaluation"] == "EXECUTED_EXPLORATORY" for c in cases),
            "unsupported": sum(c["evaluation"] == "NOT_RUN_UNSUPPORTED_SCHEMA" for c in cases),
        },
        "limitations": [
            "Scenarios designed after inspecting E1-E10 and evaluator contracts",
            "No independent reference labels or authenticated industrial evidence",
            "Unsupported E19/E20 must not be scored as successes or failures",
            "SHACL comparison pending a common RDF encoder for E11-E20",
            "All engineering authorization remains false",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="selira-e11-e20-results.json")
    args = parser.parse_args()
    payload = build()
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n",
                                 encoding="utf-8")
    for case in payload["cases"]:
        print(case["id"], case["evaluation"],
              case.get("sourceStatus", "NOT_EVALUATED"))
    print("Wrote", args.output)


if __name__ == "__main__":
    main()
