"""SC-04: configuration and revision applicability, three-valued and fail-closed.

This evaluator trusts only explicitly marked assertions within the supplied
snapshot; it does not independently authenticate sources or grant authorization.
"""

# Created: 2026-10-30
# Author: Harish
from collections.abc import Mapping


def evaluate_sc04(snapshot):
    result = {"contract": "SC-04", "caseId": None, "status": "U",
              "engineeringCertification": "U", "authorization": False,
              "evidence": [], "reasons": [],
              "limitations": ["Assertion authority is not independently authenticated",
                              "SC-04 alone never authorizes engineering use"]}
    if not isinstance(snapshot, Mapping):
        result["reasons"].append("Malformed snapshot")
        return result
    result["caseId"] = snapshot.get("caseId")
    task = snapshot.get("task")
    assertions = snapshot.get("applicabilityAssertions")
    if not isinstance(task, Mapping) or not isinstance(assertions, list):
        result["reasons"].append("Task or applicability assertions missing")
        return result
    config, revision = task.get("configuration"), task.get("revision")
    if not all(isinstance(x, str) and x.strip() for x in (config, revision)):
        result["reasons"].append("Task configuration or revision unspecified")
        return result
    usable = [a for a in assertions if isinstance(a, Mapping)
              and a.get("authority") == "AUTHENTICATED"
              and a.get("configuration") == config
              and a.get("revision") == revision
              and a.get("verdict") in ("APPLICABLE", "INAPPLICABLE")
              and isinstance(a.get("evidenceRef"), str) and a["evidenceRef"].strip()
              and isinstance(a.get("provenance"), Mapping)
              and a["provenance"].get("source")]
    result["evidence"] = [
        {"verdict": a["verdict"], "configuration": a["configuration"],
         "revision": a["revision"], "evidenceRef": a["evidenceRef"],
         "provenance": dict(a["provenance"])} for a in usable]
    verdicts = {a["verdict"] for a in usable}
    if "INAPPLICABLE" in verdicts:
        result["status"] = "F"
        result["reasons"].append("Authenticated evidence declares task configuration/revision inapplicable")
    elif verdicts == {"APPLICABLE"}:
        result["status"] = "V"
    else:
        result["reasons"].append("No authenticated applicability assertion for exact task configuration and revision")
    return result


def assess_graphdb_sc04(report):
    """Report revision/configuration observations without certifying applicability."""
    if not isinstance(report, dict) or report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB report")
    facts = report.get("facts")
    if not isinstance(facts, list):
        raise ValueError("Missing RDF facts")
    observations = []
    names = {"hasRevision", "hasStructureStatus", "hasAssociationBasis",
             "hasValidationStatus", "hasSimulationStatus"}
    for row in facts:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str)
                                                for k in ("s", "p", "o", "g")):
            raise ValueError("Malformed RDF observation")
        if row["p"].rsplit("/", 1)[-1] in names:
            observations.append({
                "subject": row["s"], "predicate": row["p"],
                "object": row["o"], "graph": row["g"],
                "classification": "UNSPECIFIED_REVISION"
                if row["p"].endswith("/hasRevision") and row["o"] == "UNSPECIFIED"
                else "DISCOVERY_ONLY_NOT_APPLICABILITY_PROOF"})
    return {"contract": "SC-04", "caseId": "SC04-T3", "status": "U",
            "engineeringCertification": "U", "authorization": False,
            "sourceStatus": report["status"],
            "sourceTruncated": report.get("truncated", True),
            "observedFacts": len(facts), "evidence": observations,
            "reasons": ["No authenticated applicability assertion for a specified task configuration and revision",
                        "UNSPECIFIED BOM revision cannot establish task applicability"],
            "limitations": ["Focused discovery cannot establish graph-wide absence",
                            "RDF source authority is not independently authenticated",
                            "SC-04 alone never authorizes engineering use"]}
