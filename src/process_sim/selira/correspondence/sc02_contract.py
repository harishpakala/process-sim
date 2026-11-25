"""SC-02 quantity-kind compatibility contract (not unit compatibility).

Assertions are caller-supplied and NOT independently authenticated here.
"""

# Created: 2026-10-30
# Author: Harish
from collections.abc import Mapping


def evaluate_sc02(evidence):
    result = {"contract": "SC-02", "caseId": None, "status": "U",
              "engineeringCertification": "U", "authorization": False,
              "reasons": [], "evidence": [],
              "limitations": ["Source authority is not independently authenticated.",
                              "SC-02 does not evaluate units, identity or live binding."]}
    if not isinstance(evidence, Mapping):
        result["reasons"].append("Malformed evidence")
        return result
    result["caseId"] = evidence.get("caseId")
    revision = evidence.get("revision")
    records = evidence.get("quantityAssertions")
    if not isinstance(revision, str) or not revision.strip() or not isinstance(records, list):
        result["reasons"].append("Revision or quantity assertions missing")
        return result
    accepted = {}
    for side in ("engineering", "operational"):
        valid = [r for r in records if isinstance(r, Mapping)
                 and r.get("side") == side
                 and isinstance(r.get("quantityKind"), str)
                 and r["quantityKind"].strip()
                 and r.get("revision") == revision
                 and r.get("authority") == "AUTHENTICATED"
                 and isinstance(r.get("evidenceRef"), str)
                 and r["evidenceRef"].strip()
                 and isinstance(r.get("provenance"), Mapping)
                 and r["provenance"].get("source")]
        result["evidence"].extend({"side": side, "quantityKind": r["quantityKind"],
                                   "evidenceRef": r["evidenceRef"],
                                   "provenance": dict(r["provenance"])} for r in valid)
        kinds = {r["quantityKind"].strip().lower() for r in valid}
        if len(kinds) == 1:
            accepted[side] = next(iter(kinds))
        elif len(kinds) > 1:
            result["status"] = "F"
            result["reasons"].append("Conflicting authenticated " + side + " quantity kinds")
        else:
            result["reasons"].append("No authenticated revision-scoped " + side + " quantity kind")
    if result["status"] != "F" and len(accepted) == 2:
        if accepted["engineering"] == accepted["operational"]:
            result["status"] = "V"
        else:
            result["status"] = "F"
            result["reasons"].append("Engineering and operational quantity kinds differ")
    return result


def assess_graphdb_sc02(report):
    """Expose RDF observations, never infer a quantity from labels or identifiers."""
    if not isinstance(report, dict) or report.get("status") != "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY":
        raise ValueError("Expected focused GraphDB discovery")
    facts = report.get("facts")
    if not isinstance(facts, list):
        raise ValueError("Missing facts")
    observed = []
    names = {"hasMeasuredVariable", "hasMappingBasis", "hasSignalName",
             "hasMappingStatus", "hasUnit"}
    for row in facts:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str)
                                                for k in ("s", "p", "o", "g")):
            raise ValueError("Invalid RDF observation")
        if row["p"].rsplit("/", 1)[-1] in names:
            observed.append({"subject": row["s"], "predicate": row["p"],
                             "object": row["o"], "graph": row["g"]})
    return {"contract": "SC-02", "caseId": "SC02-T3", "status": "U",
            "engineeringCertification": "U", "authorization": False,
            "sourceStatus": report["status"],
            "sourceTruncated": report.get("truncated", True),
            "observedFacts": len(facts), "evidence": observed,
            "reasons": ["No authenticated revision-scoped engineering and operational quantity-kind pair",
                        "Signal names and descriptive mapping text are not quantity-kind certification"],
            "limitations": ["A focused query does not prove graph-wide absence",
                            "The evaluator does not authenticate GraphDB provenance",
                            "SC-02 alone never authorizes engineering use"]}
